"""Localization baselines B1, B3, B4 (PLAN_v0.2.1 section 11.2).

All localizers receive only the observable Trace, validator flags computed from it, and (B4)
the InterventionService. B3 weights are fixed a priori (DECISIONS.md ADR-018) and are never
tuned on the test split. Scores are heuristic integers, not probabilities.
"""

from __future__ import annotations

from collections.abc import Mapping

from agenttrace.localize.observe import boundary_events, symptom_chain, symptom_seq
from agenttrace.localize.types import EvidenceLabel, Investigation, StepAssessment
from agenttrace.replay.service import InterventionService, ProbeOutcome
from agenttrace.trace.schema import Boundary, Event, EventStatus, Trace

W_CHAIN = 2  # on the argument-origin chain of the symptom
W_FLAG = 3  # at least one validator flag
W_ERROR = 1  # delivered ERROR/TIMEOUT status
W_MUTATING = 1  # committed a state change

Flags = Mapping[int, tuple[str, ...]]


def _candidates(trace: Trace, symptom: int) -> list[Event]:
    return [e for e in boundary_events(trace) if e.seq <= symptom]


def score_step(event: Event, flags: Flags, chain: set[int]) -> int:
    score = 0
    if event.seq in chain:
        score += W_CHAIN
    if flags.get(event.seq):
        score += W_FLAG
    if event.boundary is Boundary.TOOL and event.status is not EventStatus.OK:
        score += W_ERROR
    if event.state is not None and event.state.committed:
        score += W_MUTATING
    return score


def _assess(
    event: Event, flags: Flags, chain: set[int], label: EvidenceLabel, **extra: object
) -> StepAssessment:
    return StepAssessment(
        seq=event.seq,
        logical_key=event.logical_key,
        boundary=event.boundary,
        name=event.name,
        label=label,
        score=score_step(event, flags, chain),
        flags=flags.get(event.seq, ()),
        on_symptom_chain=event.seq in chain,
        **extra,  # type: ignore[arg-type]
    )


def b3_order(trace: Trace, flags: Flags) -> tuple[list[Event], int, set[int]]:
    symptom = symptom_seq(trace)
    chain = symptom_chain(trace, symptom)
    candidates = _candidates(trace, symptom)
    ordered = sorted(candidates, key=lambda e: (-score_step(e, flags, chain), e.seq))
    return ordered, symptom, chain


def rank_b1(trace: Trace, flags: Flags) -> Investigation:
    """B1 earliest visible error: flagged/error events by seq, then the symptom, then the rest."""
    symptom = symptom_seq(trace)
    chain = symptom_chain(trace, symptom)
    candidates = _candidates(trace, symptom)

    def visible(e: Event) -> bool:
        return bool(flags.get(e.seq)) or (
            e.boundary is Boundary.TOOL and e.status is not EventStatus.OK
        )

    errors = [e for e in candidates if visible(e)]
    rest = [e for e in candidates if e not in errors and e.seq != symptom]
    symptom_event = [e for e in candidates if e.seq == symptom and e not in errors]
    ordered = errors + symptom_event + rest
    ranking = tuple(_assess(e, flags, chain, EvidenceLabel.SUSPICION) for e in ordered)
    return Investigation(
        run_id=trace.header.run_id,
        method="B1",
        ranking=ranking,
        symptom_seq=symptom,
        conclusion="suspicion only",
    )


def rank_b3(trace: Trace, flags: Flags) -> Investigation:
    """B3 rule-based score, ties broken earliest-first."""
    ordered, symptom, chain = b3_order(trace, flags)
    ranking = tuple(_assess(e, flags, chain, EvidenceLabel.SUSPICION) for e in ordered)
    return Investigation(
        run_id=trace.header.run_id,
        method="B3",
        ranking=ranking,
        symptom_seq=symptom,
        conclusion="suspicion only",
    )


def rank_b4(service: InterventionService, flags: Flags) -> Investigation:
    """B4 earliest reference deviation: deviating steps by seq, then the rest in B3 order."""
    trace = service.trace
    ordered, symptom, chain = b3_order(trace, flags)
    probes = {e.seq: service.reference_deviation(e.seq) for e in ordered}
    deviating = sorted(
        (e for e in ordered if probes[e.seq].outcome is ProbeOutcome.DEVIATES), key=lambda e: e.seq
    )
    rest = [e for e in ordered if e not in deviating]
    ranking: list[StepAssessment] = []
    for event in deviating + rest:
        probe = probes[event.seq]
        label = {
            ProbeOutcome.DEVIATES: EvidenceLabel.REFERENCE_DEVIATION,
            ProbeOutcome.CONSISTENT: EvidenceLabel.SUSPICION,
            ProbeOutcome.UNSUPPORTED: EvidenceLabel.UNSUPPORTED,
        }[probe.outcome]
        reference = probe.outcome.value + (f" ({probe.reason})" if probe.reason else "")
        ranking.append(_assess(event, flags, chain, label, reference=reference))
    return Investigation(
        run_id=trace.header.run_id,
        method="B4",
        ranking=tuple(ranking),
        symptom_seq=symptom,
        conclusion="reference deviations only (no interventions)",
        unsupported=tuple(s.seq for s in ranking if s.label is EvidenceLabel.UNSUPPORTED),
        replays_used=service.replays_used,
    )
