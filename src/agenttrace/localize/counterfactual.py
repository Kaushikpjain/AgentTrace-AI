"""CF: placebo-controlled single-step counterfactual localizer (PLAN_v0.2.1 section 11.2).

Candidates are ordered by B3. Each candidate is probed against its trusted reference. Steps
consistent with their reference are not intervened on; deviating steps get a default
intervention (tools: EXECUTION_REPLACEMENT with REFERENCE_TOOL; decisions:
OBSERVATION_REPLACEMENT with REFERENCE_POLICY) plus a same-type placebo.

A step is labelled INTERVENTIONAL_REPAIR only if the intervention turned FAIL into PASS AND the
placebo reproduced the original run. This means "sufficient to repair this run", never "the
unique cause". All repair sites are reported.
"""

from __future__ import annotations

from collections.abc import Mapping

from agenttrace.localize.baselines import b3_order, score_step
from agenttrace.localize.types import NOT_ISOLATED, EvidenceLabel, Investigation, StepAssessment
from agenttrace.replay.counterfactual import CounterfactualStatus
from agenttrace.replay.service import InterventionService, ProbeOutcome
from agenttrace.trace.schema import Outcome


def rank_cf(service: InterventionService, flags: Mapping[int, tuple[str, ...]]) -> Investigation:
    trace = service.trace
    ordered, symptom, chain = b3_order(trace, flags)
    notes: list[str] = []
    if trace.footer.outcome.outcome is not Outcome.FAIL:
        notes.append("run did not fail: interventions cannot demonstrate a repair")

    assessments: list[StepAssessment] = []
    for event in ordered:
        probe = service.reference_deviation(event.seq)
        reference = probe.outcome.value + (f" ({probe.reason})" if probe.reason else "")
        experiment = None
        note = ""
        if probe.outcome is ProbeOutcome.UNSUPPORTED:
            label = EvidenceLabel.UNSUPPORTED
            note = probe.reason or ""
        elif probe.outcome is ProbeOutcome.CONSISTENT:
            label = EvidenceLabel.SUSPICION
        else:
            experiment = service.experiment(event.seq)
            if experiment.intervention_status is not CounterfactualStatus.COMPLETED:
                label = EvidenceLabel.UNSUPPORTED
                note = experiment.reason or experiment.intervention_status.value
            elif experiment.interventional_repair:
                label = EvidenceLabel.INTERVENTIONAL_REPAIR
            else:
                label = EvidenceLabel.REFERENCE_DEVIATION
                if experiment.repair_observed and not experiment.placebo_valid:
                    note = "repair observed but placebo invalid: evidence not upgraded"
        score = score_step(event, flags, chain)
        assessments.append(
            StepAssessment(
                seq=event.seq,
                logical_key=event.logical_key,
                boundary=event.boundary,
                name=event.name,
                label=label,
                score=score,
                flags=flags.get(event.seq, ()),
                on_symptom_chain=event.seq in chain,
                reference=reference,
                experiment=experiment,
                note=note,
            )
        )

    tier = {
        EvidenceLabel.INTERVENTIONAL_REPAIR: 0,
        EvidenceLabel.REFERENCE_DEVIATION: 1,
        EvidenceLabel.SUSPICION: 2,
        EvidenceLabel.UNSUPPORTED: 3,
    }
    b3_position = {e.seq: i for i, e in enumerate(ordered)}
    ranking = sorted(
        assessments,
        key=lambda a: (
            tier[a.label],
            a.seq if tier[a.label] <= 1 else b3_position[a.seq],
        ),
    )
    repairs = tuple(a.seq for a in ranking if a.label is EvidenceLabel.INTERVENTIONAL_REPAIR)
    conclusion = (
        "repair sites: " + ", ".join(f"seq {s}" for s in repairs) if repairs else NOT_ISOLATED
    )
    return Investigation(
        run_id=trace.header.run_id,
        method="CF",
        ranking=tuple(ranking),
        symptom_seq=symptom,
        conclusion=conclusion,
        repair_sites=repairs,
        unsupported=tuple(a.seq for a in ranking if a.label is EvidenceLabel.UNSUPPORTED),
        replays_used=service.replays_used,
        notes=tuple(notes),
    )
