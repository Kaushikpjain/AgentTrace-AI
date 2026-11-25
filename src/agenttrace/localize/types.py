"""Localization result types and evidence labels (PLAN_v0.2.1 section 11.3, REPLAY_SPEC §14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from agenttrace.replay.service import ExperimentSummary
from agenttrace.trace.schema import Boundary


class EvidenceLabel(StrEnum):
    SUSPICION = "SUSPICION"
    REFERENCE_DEVIATION = "REFERENCE_DEVIATION"
    INTERVENTIONAL_REPAIR = "INTERVENTIONAL_REPAIR"
    UNSUPPORTED = "UNSUPPORTED"


NOT_ISOLATED = "NOT_ISOLATED"  # the run FAILED and no single-step intervention repaired it
# The original run did not fail, so there is nothing to localize or repair (post-freeze, ADR-025).
NO_FAILURE = "NO_FAILURE"
# The oracle produced no verdict, so repair cannot be judged.
NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class StepAssessment:
    seq: int
    logical_key: str
    boundary: Boundary
    name: str
    label: EvidenceLabel
    score: int  # B3 heuristic score (integer weights fixed a priori; not a probability)
    flags: tuple[str, ...] = ()  # supporting observations from validators
    on_symptom_chain: bool = False
    reference: str | None = None  # DEVIATES / CONSISTENT / UNSUPPORTED (+ reason)
    experiment: ExperimentSummary | None = None
    note: str = ""


@dataclass(frozen=True)
class Investigation:
    run_id: str
    method: str
    ranking: tuple[StepAssessment, ...]
    symptom_seq: int
    # CF: "repair sites: ..." | NOT_ISOLATED | NO_FAILURE | NOT_EVALUATED; baselines: fixed text
    conclusion: str
    repair_sites: tuple[int, ...] = ()
    unsupported: tuple[int, ...] = ()
    replays_used: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def top(self) -> StepAssessment | None:
        return self.ranking[0] if self.ranking else None

    def rank_of(self, seq: int) -> int | None:
        for index, step in enumerate(self.ranking, start=1):
            if step.seq == seq:
                return index
        return None
