"""Positional, consume-once cassette over a recorded run (REPLAY_SPEC section 6)."""

from __future__ import annotations

from dataclasses import dataclass

from agenttrace.runtime.gateway import DivergenceDetected
from agenttrace.trace.schema import (
    Boundary,
    Divergence,
    DivergenceKind,
    Event,
    LedgerEntry,
    RunRecord,
)


class CassetteFenceViolation(RuntimeError):
    """A lookup after the cassette was closed. Always a bug: never catch and continue."""


@dataclass(frozen=True)
class CassetteEntry:
    event: Event
    ledger: LedgerEntry


class Cassette:
    """Boundary events of a recording, served strictly in order and verified on every lookup."""

    constructed = (
        0  # process-wide count, used by correctness checks (regression must not build one)
    )

    def __init__(self, record: RunRecord) -> None:
        Cassette.constructed += 1
        boundary = [e for e in record.events if e.boundary in (Boundary.DECISION, Boundary.TOOL)]
        if len(boundary) != len(record.ledger):
            raise ValueError("record has mismatched events and ledger")
        self._entries = [
            CassetteEntry(event, entry)
            for event, entry in zip(boundary, record.ledger, strict=True)
        ]
        self._position = 0
        self._closed = False
        self.accesses = 0

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def position(self) -> int:
        return self._position

    @property
    def remaining(self) -> int:
        return len(self._entries) - self._position

    def close(self) -> None:
        """Fence: no further lookups are allowed (REPLAY_INTERVENE, Week 3)."""
        self._closed = True

    def peek_seq(self) -> int | None:
        return self._entries[self._position].event.seq if self.remaining else None

    def expect(self, seq: int, boundary: Boundary, name: str, request_fp: str) -> CassetteEntry:
        """Consume the next entry if it matches (boundary, name, request_fp); else diverge."""
        if self._closed:
            raise CassetteFenceViolation(f"cassette lookup at seq {seq} after the fence")
        self.accesses += 1

        def diverge(kind: DivergenceKind, detail: str, expected: str | None = None) -> None:
            raise DivergenceDetected(
                Divergence(
                    seq=seq,
                    kind=kind,
                    expected_fp=expected,
                    actual_fp=request_fp if kind is DivergenceKind.REQUEST else None,
                    detail=detail,
                )
            )

        if self._position >= len(self._entries):
            diverge(
                DivergenceKind.MISSING_EVENT,
                f"replay requested {boundary.value}:{name} but the cassette is exhausted",
            )
        entry = self._entries[self._position]
        recorded = entry.event
        if recorded.boundary is not boundary or recorded.seq != seq:
            diverge(
                DivergenceKind.BOUNDARY,
                f"expected {recorded.boundary.value} at seq {recorded.seq}, "
                f"replay produced {boundary.value} at seq {seq}",
            )
        if recorded.name != name:
            diverge(DivergenceKind.NAME, f"expected {recorded.name!r}, replay called {name!r}")
        if recorded.request_fp != request_fp:
            diverge(
                DivergenceKind.REQUEST,
                f"request for {name!r} differs from the recording",
                expected=recorded.request_fp,
            )
        self._position += 1
        return entry
