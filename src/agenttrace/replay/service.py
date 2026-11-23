"""InterventionService: the only channel through which localizers reach privileged data.

It is bound to a full (privileged) RunRecord but exposes only observable facts: the
observable Trace, reference-deviation verdicts, and experiment summaries made of outcomes,
statuses and booleans. It never returns ledger contents, raw outputs, fault plans, labels
or the counterfactual runs themselves (whose ledgers would reveal fault applications).
"""

from __future__ import annotations

from dataclasses import dataclass

from agenttrace.replay.counterfactual import (
    CounterfactualStatus,
    ProbeOutcome,
    ProbeResult,
    default_request,
    probe_reference,
    run_experiment,
)
from agenttrace.replay.exact import ReplayContext
from agenttrace.trace.schema import InterventionType, Outcome, ReferenceSource, RunRecord, Trace


@dataclass(frozen=True)
class ExperimentSummary:
    target_seq: int
    intervention_type: InterventionType | None
    reference_source: ReferenceSource | None
    original_outcome: Outcome
    intervention_status: CounterfactualStatus
    intervention_outcome: Outcome | None
    placebo_status: CounterfactualStatus | None
    placebo_outcome: Outcome | None
    placebo_valid: bool
    repair_observed: bool
    reason: str | None = None
    cassette_accesses_after_fence: int = 0  # max over intervention and placebo (must be 0)

    @property
    def interventional_repair(self) -> bool:
        return self.repair_observed and self.placebo_valid


class InterventionService:
    def __init__(self, record: RunRecord, ctx: ReplayContext) -> None:
        self.__record = record
        self.__ctx = ctx
        self.__probes: dict[int, ProbeResult] = {}
        self.__experiments: dict[int, ExperimentSummary] = {}
        self.replays_used = 0

    @property
    def trace(self) -> Trace:
        return self.__record.observable()

    def reference_deviation(self, seq: int) -> ProbeResult:
        if seq not in self.__probes:
            self.replays_used += 1
            self.__probes[seq] = probe_reference(self.__record, self.__ctx, seq)
        return self.__probes[seq]

    def experiment(self, seq: int) -> ExperimentSummary:
        if seq in self.__experiments:
            return self.__experiments[seq]
        original_outcome = self.__record.footer.outcome.outcome
        request = default_request(self.__record, seq)
        if request is None:
            summary = ExperimentSummary(
                seq,
                None,
                None,
                original_outcome,
                CounterfactualStatus.UNSUPPORTED,
                None,
                None,
                None,
                False,
                False,
                "target_not_boundary",
            )
        else:
            self.replays_used += 2  # reference intervention + placebo
            result = run_experiment(self.__record, self.__ctx, request)
            summary = ExperimentSummary(
                target_seq=seq,
                intervention_type=request.intervention_type,
                reference_source=request.reference_source,
                original_outcome=original_outcome,
                intervention_status=result.intervention.status,
                intervention_outcome=result.intervention.outcome,
                placebo_status=result.placebo.status,
                placebo_outcome=result.placebo.outcome,
                placebo_valid=result.placebo_valid,
                repair_observed=result.repair_observed,
                reason=result.intervention.reason,
                cassette_accesses_after_fence=max(
                    result.intervention.cassette_accesses_after_fence,
                    result.placebo.cassette_accesses_after_fence,
                ),
            )
        self.__experiments[seq] = summary
        return summary


__all__ = ["ExperimentSummary", "InterventionService", "ProbeOutcome", "ProbeResult"]
