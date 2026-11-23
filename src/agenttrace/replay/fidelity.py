"""Replay fidelity metrics (REPLAY_SPEC section 11): computed, never assumed."""

from __future__ import annotations

from dataclasses import dataclass

from agenttrace.trace.schema import Boundary, Event, LedgerEntry, RunRecord


@dataclass(frozen=True)
class Ratio:
    matched: int
    total: int

    @property
    def complete(self) -> bool:
        return self.matched == self.total

    def __str__(self) -> str:
        return f"{self.matched}/{self.total}"


@dataclass(frozen=True)
class FidelityReport:
    response_equality: Ratio  # delivered response fingerprints, all boundary events
    event_sequence: Ratio  # (boundary, name, request_fp), positional
    event_sequence_agreement: bool  # identical sequence and length
    raw_result_agreement: Ratio  # tool events: executed flag + raw output fp + fault applications
    state_transition_agreement: Ratio  # tool events: committed, before_hash, after_hash
    final_state_equal: bool
    outcome_equal: bool

    @property
    def exact(self) -> bool:
        return (
            self.response_equality.complete
            and self.event_sequence_agreement
            and self.raw_result_agreement.complete
            and self.state_transition_agreement.complete
            and self.final_state_equal
            and self.outcome_equal
        )


def _pairs(record: RunRecord) -> list[tuple[Event, LedgerEntry]]:
    events = [e for e in record.events if e.boundary in (Boundary.DECISION, Boundary.TOOL)]
    return list(zip(events, record.ledger, strict=True))


def outcome_key(record: RunRecord) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    footer = record.footer
    clauses = tuple((c.clause_id, c.message) for c in footer.outcome.violated_clauses)
    return footer.status.value, footer.outcome.outcome.value, clauses


def compute_fidelity(original: RunRecord, replay: RunRecord) -> FidelityReport:
    orig, rep = _pairs(original), _pairs(replay)
    orig_tools = [(e, entry) for e, entry in orig if e.boundary is Boundary.TOOL]
    rep_tools = [(e, entry) for e, entry in rep if e.boundary is Boundary.TOOL]

    def key(event: Event) -> tuple[str, str, str | None]:
        return event.boundary.value, event.name, event.request_fp

    response = sum(
        a.response_fp == b.response_fp for (a, _), (b, _) in zip(orig, rep, strict=False)
    )
    sequence = sum(key(a) == key(b) for (a, _), (b, _) in zip(orig, rep, strict=False))
    raw = sum(
        (x.executed, x.raw_output_fp, x.fault_applications)
        == (y.executed, y.raw_output_fp, y.fault_applications)
        for (_, x), (_, y) in zip(orig_tools, rep_tools, strict=False)
    )
    state = sum(
        a.state == b.state
        or (
            a.state is not None
            and b.state is not None
            and (a.state.committed, a.state.before_hash, a.state.after_hash)
            == (b.state.committed, b.state.before_hash, b.state.after_hash)
        )
        for (a, _), (b, _) in zip(orig_tools, rep_tools, strict=False)
    )
    return FidelityReport(
        response_equality=Ratio(response, len(orig)),
        event_sequence=Ratio(sequence, len(orig)),
        event_sequence_agreement=len(orig) == len(rep) and sequence == len(orig),
        raw_result_agreement=Ratio(raw, len(orig_tools)),
        state_transition_agreement=Ratio(state, len(orig_tools)),
        final_state_equal=original.footer.final_state_hash == replay.footer.final_state_hash,
        outcome_equal=outcome_key(original) == outcome_key(replay),
    )
