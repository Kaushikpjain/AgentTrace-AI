"""Build self-consistent tampered recordings (valid fingerprints, seq and hash chain).

These model a cassette produced by *different* code or state, so that detection must come
from the replay engine itself, not from the store's integrity checks.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.integrity import compute_chain_root
from agenttrace.trace.schema import Boundary, Event, LedgerEntry, RunRecord, Totals
from agenttrace.trace.store import validate_record


def rebuild(record: RunRecord, events: Iterable[Event], ledger: Iterable[LedgerEntry]) -> RunRecord:
    events, ledger = tuple(events), tuple(ledger)
    footer = record.footer.model_copy(
        update={
            "totals": Totals(
                events=len(events),
                decisions=sum(e.boundary is Boundary.DECISION for e in events),
                tool_calls=sum(e.boundary is Boundary.TOOL for e in events),
                steps=sum(e.boundary is Boundary.AGENT_STEP for e in events),
            ),
            "integrity": record.footer.integrity.model_copy(
                update={
                    "event_count": len(events),
                    "ledger_count": len(ledger),
                    "chain_root": compute_chain_root(record.header, events, ledger),
                }
            ),
        }
    )
    rebuilt = RunRecord(
        header=record.header,
        events=events,
        ledger=ledger,
        footer=footer,
        fault_plan=record.fault_plan,
    )
    validate_record(rebuilt)  # the tampered cassette is internally consistent
    return rebuilt


def revalidated(model: Any, **changes: Any) -> Any:
    """Copy a pydantic model with changes, recomputing payload fingerprints, and validate."""
    data = model.model_dump(mode="python")
    data.update(changes)
    for payload, fp_field in (
        ("request", "request_fp"),
        ("response", "response_fp"),
        ("raw_output", "raw_output_fp"),
    ):
        if payload in changes and fp_field in data:
            data[fp_field] = fingerprint(changes[payload]) if changes[payload] is not None else None
    return type(model).model_validate(data)


def tool_seqs(record: RunRecord, name: str) -> list[int]:
    return [e.seq for e in record.events if e.boundary is Boundary.TOOL and e.name == name]


def map_event(record: RunRecord, seq: int, fn: Callable[[Event], Event]) -> RunRecord:
    events = [fn(e) if e.seq == seq else e for e in record.events]
    return rebuild(record, events, record.ledger)


def map_ledger(record: RunRecord, seq: int, fn: Callable[[LedgerEntry], LedgerEntry]) -> RunRecord:
    ledger = [fn(entry) if entry.seq == seq else entry for entry in record.ledger]
    return rebuild(record, record.events, ledger)


def drop_events(record: RunRecord, seqs: set[int]) -> RunRecord:
    """Remove events (and their ledger entries), renumbering seq contiguously."""
    kept = [e for e in record.events if e.seq not in seqs]
    kept_ledger = [entry for entry in record.ledger if entry.seq not in seqs]
    renumber = {e.seq: i for i, e in enumerate(kept)}
    events = [e.model_copy(update={"seq": renumber[e.seq]}) for e in kept]
    ledger = [entry.model_copy(update={"seq": renumber[entry.seq]}) for entry in kept_ledger]
    return rebuild(record, events, ledger)


def with_run_id(record: RunRecord, run_id: str) -> RunRecord:
    """Same recording under a different run id (header and events updated, chain rebuilt)."""
    header = record.header.model_copy(update={"run_id": run_id})
    events = [e.model_copy(update={"run_id": run_id}) for e in record.events]
    renamed = record.model_copy(update={"header": header})
    return rebuild(renamed, events, record.ledger)
