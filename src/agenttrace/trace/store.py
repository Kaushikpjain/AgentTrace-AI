"""TraceStore protocol and JSONL implementation (TRACE_SCHEMA.md sections 1 and 7, ADR-003).

Each run is stored as ``<root>/<run_id>/{header.json, events.jsonl, ledger.jsonl, footer.json}``.
Writes go to a hidden temp directory that is atomically renamed; recordings are immutable.
``load_ledger`` is privileged: localizer code must not call it (ADR-009).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from agenttrace.trace.canonical import canonical_bytes
from agenttrace.trace.integrity import compute_chain_root
from agenttrace.trace.schema import (
    Boundary,
    Event,
    LedgerEntry,
    RunFooter,
    RunHeader,
    RunRecord,
    Trace,
    UnsupportedSchemaVersion,
    check_schema_version,
)

MAX_FILE_BYTES = 64 * 1024 * 1024
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

HEADER_FILE = "header.json"
EVENTS_FILE = "events.jsonl"
LEDGER_FILE = "ledger.jsonl"
FOOTER_FILE = "footer.json"


class TraceStoreError(Exception):
    """Base class for store errors."""


class RunNotFoundError(TraceStoreError):
    pass


class RunExistsError(TraceStoreError):
    pass


class CorruptTraceError(TraceStoreError):
    """Unparseable, oversized or structurally broken files."""


class TraceSchemaError(TraceStoreError):
    """A document parsed but failed schema validation."""


class TraceIntegrityError(TraceStoreError):
    """Cross-record consistency or hash-chain check failed."""


class IncompleteRecordingError(TraceStoreError):
    """The recording has no footer (interrupted or partially written)."""


class TraceStore(Protocol):
    def save(self, record: RunRecord) -> None: ...

    def load_trace(self, run_id: str) -> Trace: ...

    def load_ledger(self, run_id: str) -> tuple[LedgerEntry, ...]: ...

    def list_run_ids(self) -> list[str]: ...

    def exists(self, run_id: str) -> bool: ...


def validate_record(record: RunRecord) -> None:
    """Cross-record checks shared by save and load (TRACE_SCHEMA.md section 7, steps 3-6)."""
    header, events, ledger, footer = record.header, record.events, record.ledger, record.footer
    seen_steps: set[str] = set()
    for index, event in enumerate(events):
        if event.run_id != header.run_id:
            raise TraceIntegrityError(f"event seq={event.seq} has run_id {event.run_id!r}")
        if event.seq != index:
            raise TraceIntegrityError(f"seq not contiguous: expected {index}, got {event.seq}")
        if event.parent_span_id is not None and event.parent_span_id not in seen_steps:
            raise TraceIntegrityError(f"event seq={event.seq} references unknown parent span")
        if event.boundary is Boundary.AGENT_STEP:
            seen_steps.add(event.span_id)
    boundary_events = [e for e in events if e.boundary in (Boundary.DECISION, Boundary.TOOL)]
    if len(boundary_events) != len(ledger):
        raise TraceIntegrityError(
            f"ledger has {len(ledger)} entries for {len(boundary_events)} boundary events"
        )
    for event, entry in zip(boundary_events, ledger, strict=True):
        if (event.seq, event.boundary) != (entry.seq, entry.boundary):
            raise TraceIntegrityError(f"ledger entry seq={entry.seq} does not match its event")
    integrity = footer.integrity
    if integrity.event_count != len(events) or integrity.ledger_count != len(ledger):
        raise TraceIntegrityError("integrity counts do not match the recording")
    if integrity.chain_root != compute_chain_root(events, ledger):
        raise TraceIntegrityError("hash chain mismatch: recording was modified or truncated")


class JsonlTraceStore:
    """File-based TraceStore. Safe for a single writer process (MVP)."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------------ helpers
    def _run_dir(self, run_id: str) -> Path:
        if not _RUN_ID_RE.match(run_id):
            raise TraceStoreError(f"invalid run id: {run_id!r}")
        return self.root / run_id

    @staticmethod
    def _line(model: BaseModel) -> bytes:
        return canonical_bytes(model) + b"\n"

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        with path.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _read_bytes(path: Path) -> bytes:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise CorruptTraceError(f"{path.name} exceeds {MAX_FILE_BYTES} bytes")
        return path.read_bytes()

    def _parse_doc(self, path: Path) -> Any:
        try:
            return json.loads(self._read_bytes(path))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CorruptTraceError(f"{path.name}: invalid JSON ({exc})") from exc

    def _parse_lines(self, path: Path) -> list[tuple[int, Any]]:
        out: list[tuple[int, Any]] = []
        for lineno, raw in enumerate(self._read_bytes(path).splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                out.append((lineno, json.loads(raw)))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise CorruptTraceError(f"{path.name}:{lineno}: invalid JSON ({exc})") from exc
        return out

    @staticmethod
    def _validate[M: BaseModel](model: type[M], data: Any, where: str) -> M:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise TraceSchemaError(f"{where}: {exc.error_count()} schema error(s): {exc}") from exc

    # ------------------------------------------------------------------ API
    def exists(self, run_id: str) -> bool:
        return self._run_dir(run_id).is_dir()

    def list_run_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            p.name for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(".")
        )

    def save(self, record: RunRecord) -> None:
        validate_record(record)
        final = self._run_dir(record.header.run_id)
        if final.exists():
            raise RunExistsError(f"run {record.header.run_id} already exists (immutable)")
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".tmp-{record.header.run_id}-{uuid.uuid4().hex[:8]}"
        tmp.mkdir()
        try:
            self._write(tmp / HEADER_FILE, canonical_bytes(record.header))
            self._write(tmp / EVENTS_FILE, b"".join(self._line(e) for e in record.events))
            self._write(tmp / LEDGER_FILE, b"".join(self._line(e) for e in record.ledger))
            self._write(tmp / FOOTER_FILE, canonical_bytes(record.footer))
            os.rename(tmp, final)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    def _load_record(self, run_id: str) -> RunRecord:
        run_dir = self._run_dir(run_id)
        if not run_dir.is_dir():
            raise RunNotFoundError(f"run {run_id} not found under {self.root}")
        for name in (HEADER_FILE, EVENTS_FILE, LEDGER_FILE):
            if not (run_dir / name).is_file():
                raise CorruptTraceError(f"run {run_id}: missing {name}")
        if not (run_dir / FOOTER_FILE).is_file():
            raise IncompleteRecordingError(f"run {run_id}: no footer (incomplete recording)")

        header_data = self._parse_doc(run_dir / HEADER_FILE)
        if not isinstance(header_data, dict):
            raise TraceSchemaError(f"{HEADER_FILE}: expected an object")
        try:
            check_schema_version(str(header_data.get("schema_version", "")))
        except UnsupportedSchemaVersion as exc:
            raise TraceSchemaError(str(exc)) from exc
        header = self._validate(RunHeader, header_data, HEADER_FILE)
        events = tuple(
            self._validate(Event, data, f"{EVENTS_FILE}:{lineno}")
            for lineno, data in self._parse_lines(run_dir / EVENTS_FILE)
        )
        ledger = tuple(
            self._validate(LedgerEntry, data, f"{LEDGER_FILE}:{lineno}")
            for lineno, data in self._parse_lines(run_dir / LEDGER_FILE)
        )
        footer = self._validate(RunFooter, self._parse_doc(run_dir / FOOTER_FILE), FOOTER_FILE)
        record = RunRecord(header=header, events=events, ledger=ledger, footer=footer)
        if header.run_id != run_id:
            raise TraceIntegrityError(f"header run_id {header.run_id!r} != directory {run_id!r}")
        validate_record(record)
        return record

    def load_trace(self, run_id: str) -> Trace:
        """Load and fully validate a run; return only the observable trace."""
        return self._load_record(run_id).observable()

    def load_ledger(self, run_id: str) -> tuple[LedgerEntry, ...]:
        """PRIVILEGED: replay engine and benchmark validator only (ADR-009)."""
        return self._load_record(run_id).ledger

    def load_record(self, run_id: str) -> RunRecord:
        """PRIVILEGED: full record including the ledger (replay engine only)."""
        return self._load_record(run_id)
