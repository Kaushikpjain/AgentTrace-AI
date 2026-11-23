"""REGRESSION: fresh execution of a candidate agent against a recorded scenario + fixture.

Authoritative semantics: docs/REPLAY_SPEC.md section 5.4.

Only the baseline's *header* (scenario, oracle, max_steps), its *fault plan* and its recorded
*outcome* are used. Its events and ledger are never read, no cassette is constructed, and no
recorded decision is reused. DECISION-stage faults (simulated agent errors) are dropped from
the fixture; environment faults (PRE/POST_EXECUTION) are kept.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from agenttrace.replay.exact import ReplayContext
from agenttrace.runtime.loop import run_episode
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    AgentRef,
    FaultPlan,
    FaultStage,
    Outcome,
    RunHeader,
    RunMode,
    RunRecord,
)
from agenttrace.trace.semantic import semantic_fingerprint
from agenttrace.trace.store import TraceStore


class RegressionVerdict(StrEnum):
    DETERMINISTIC_PASS = "DETERMINISTIC_PASS"
    DETERMINISTIC_FAIL = "DETERMINISTIC_FAIL"
    PROBABILISTIC = "PROBABILISTIC"
    CONFIG_ERROR = "CONFIG_ERROR"


class RegressionComparison(StrEnum):
    FIXED = "FIXED"
    STILL_FAILING = "STILL_FAILING"
    REGRESSED = "REGRESSED"
    STILL_PASSING = "STILL_PASSING"
    UNDETERMINED = "UNDETERMINED"


def environment_fixture(plan: FaultPlan | None) -> tuple[FaultPlan | None, tuple[str, ...]]:
    """Keep environment-side faults; return (fixture, dropped DECISION-stage fault ids)."""
    if plan is None:
        return None, ()
    kept = tuple(f for f in plan.faults if f.stage is not FaultStage.DECISION)
    dropped = tuple(f.fault_id for f in plan.faults if f.stage is FaultStage.DECISION)
    if not kept:
        return None, dropped
    return FaultPlan(plan_id=f"{plan.plan_id}:env-fixture", faults=kept), dropped


def wilson_interval(passes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for a pass rate (used for non-deterministic verdicts)."""
    if n == 0:
        return 0.0, 1.0
    p = passes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class RegressionReport:
    verdict: RegressionVerdict
    comparison: RegressionComparison
    baseline_run_id: str
    baseline_outcome: Outcome
    candidate: AgentRef | None
    runs: tuple[RunRecord, ...] = ()
    passes: int = 0
    deterministic_reproduced: bool = False
    config_differences: tuple[str, ...] = ()
    dropped_decision_faults: tuple[str, ...] = ()
    fixture_hash: str | None = None
    detail: str = ""

    @property
    def n(self) -> int:
        return len(self.runs)

    @property
    def pass_rate_interval(self) -> tuple[float, float]:
        return wilson_interval(self.passes, self.n)


def _differences(baseline: RunHeader, candidate: RunHeader) -> tuple[str, ...]:
    diffs: list[str] = []
    if baseline.agent.policy_version != candidate.agent.policy_version:
        diffs.append(
            f"agent version: {baseline.agent.policy_version} -> {candidate.agent.policy_version}"
        )
    if baseline.agent.source_hash != candidate.agent.source_hash:
        diffs.append("agent source code changed")
    if baseline.tool_manifest_hash != candidate.tool_manifest_hash:
        diffs.append("tool manifest changed")
    if baseline.fault_plan_hash != candidate.fault_plan_hash:
        diffs.append("fault plan reduced to its environment fixture")
    if baseline.scenario != candidate.scenario:
        diffs.append("scenario changed")
    if baseline.oracle != candidate.oracle:
        diffs.append("oracle changed")
    return tuple(diffs)


def run_regression(
    baseline_header: RunHeader,
    baseline_fault_plan: FaultPlan | None,
    baseline_outcome: Outcome,
    ctx: ReplayContext,
    *,
    policy_version: str,
    repeats: int = 2,
) -> RegressionReport:
    """Execute the candidate ``policy_version`` freshly ``repeats`` times (no cassette)."""
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    policy_id = baseline_header.agent.policy_id
    policy = ctx.make_policy(policy_id, policy_version)
    fixture, dropped = environment_fixture(baseline_fault_plan)
    if policy is None:
        return RegressionReport(
            verdict=RegressionVerdict.CONFIG_ERROR,
            comparison=RegressionComparison.UNDETERMINED,
            baseline_run_id=baseline_header.run_id,
            baseline_outcome=baseline_outcome,
            candidate=None,
            detail=f"unknown candidate policy {policy_id}:{policy_version}",
        )
    runs = tuple(
        run_episode(
            ctx.build_episode(baseline_header, fixture),
            policy,
            mode=RunMode.REGRESSION,
            parent_run_id=baseline_header.run_id,
        )
        for _ in range(repeats)
    )
    passes = sum(r.footer.outcome.outcome is Outcome.PASS for r in runs)
    reproduced = len(runs) >= 2 and len({semantic_fingerprint(r) for r in runs}) == 1
    if policy.deterministic and reproduced:
        verdict = (
            RegressionVerdict.DETERMINISTIC_PASS
            if passes == len(runs)
            else RegressionVerdict.DETERMINISTIC_FAIL
        )
        candidate_pass: bool | None = passes == len(runs)
    else:
        verdict = RegressionVerdict.PROBABILISTIC
        candidate_pass = None  # a pass rate, not a verdict (Level 2: k-run statistics)
    baseline_pass = baseline_outcome is Outcome.PASS
    if candidate_pass is None:
        comparison = RegressionComparison.UNDETERMINED
    elif candidate_pass:
        comparison = (
            RegressionComparison.STILL_PASSING if baseline_pass else RegressionComparison.FIXED
        )
    else:
        comparison = (
            RegressionComparison.REGRESSED if baseline_pass else RegressionComparison.STILL_FAILING
        )
    return RegressionReport(
        verdict=verdict,
        comparison=comparison,
        baseline_run_id=baseline_header.run_id,
        baseline_outcome=baseline_outcome,
        candidate=runs[0].header.agent,
        runs=runs,
        passes=passes,
        deterministic_reproduced=reproduced,
        config_differences=_differences(baseline_header, runs[0].header),
        dropped_decision_faults=dropped,
        fixture_hash=fingerprint(fixture) if fixture is not None else None,
    )


def regression_from_store(
    store: TraceStore,
    run_id: str,
    ctx: ReplayContext,
    *,
    policy_version: str,
    repeats: int = 2,
) -> RegressionReport:
    """Regression against a stored baseline. Only header, fault plan and outcome are used."""
    record = store.load_record(run_id)
    return run_regression(
        record.header,
        record.fault_plan,
        record.footer.outcome.outcome,
        ctx,
        policy_version=policy_version,
        repeats=repeats,
    )
