"""Evaluation driver: record instances and run localizers. Never reads benchmark labels.

For each instance of one split:
1. record it (scenario + fault plan; the plan never reaches localizers);
2. verify strict replay (correctness check);
3. run every requested localizer on the observable trace (B1, B3) or through an
   InterventionService (B4, CF);
4. serialize the investigations to JSON-pure dicts.

Labels are joined afterwards by ``agenttrace.bench.metrics``. That separation means the
localizer path can be audited as label-free.

Held-out instances (split ``test``) are refused without a ``HeldOutAuthorization``
(``agenttrace.bench.heldout``); this is an operational safeguard, not a security boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agenttrace.bench.heldout import HeldOutAuthorization, require_authorization
from agenttrace.env.support.scenario import load_scenario
from agenttrace.evals.validators import support_flags
from agenttrace.localize.baselines import b3_order, rank_b1, rank_b3, rank_b4
from agenttrace.localize.counterfactual import rank_cf
from agenttrace.localize.types import Investigation
from agenttrace.replay.cassette import Cassette
from agenttrace.replay.exact import ReplayContext, replay_strict
from agenttrace.replay.regression import run_regression
from agenttrace.replay.service import InterventionService
from agenttrace.runner import record_scenario
from agenttrace.trace.schema import FaultPlan, FaultStage, RunRecord

METHODS = ("B1", "B3", "B4", "CF")


def record_instance(
    instance: dict[str, Any], *, authorization: HeldOutAuthorization | None = None
) -> RunRecord:
    require_authorization(instance["split"], authorization)
    plan = FaultPlan.model_validate(instance["fault_plan"]) if instance["fault_plan"] else None
    return record_scenario(
        load_scenario(instance["scenario_id"]),
        policy_version=instance["policy_version"],
        fault_plan=plan,
    )


def _investigation_json(inv: Investigation) -> dict[str, Any]:
    steps = []
    for step in inv.ranking:
        exp = step.experiment
        steps.append(
            {
                "seq": step.seq,
                "label": step.label.value,
                "score": step.score,
                "note": step.note,
                "reference": step.reference,
                "experiment": None
                if exp is None
                else {
                    "type": exp.intervention_type.value if exp.intervention_type else None,
                    "source": exp.reference_source.value if exp.reference_source else None,
                    "status": exp.intervention_status.value,
                    "outcome": exp.intervention_outcome.value if exp.intervention_outcome else None,
                    "placebo_status": exp.placebo_status.value if exp.placebo_status else None,
                    "placebo_outcome": exp.placebo_outcome.value if exp.placebo_outcome else None,
                    "placebo_valid": exp.placebo_valid,
                    "repair_observed": exp.repair_observed,
                    "reason": exp.reason,
                    "cassette_accesses_after_fence": exp.cassette_accesses_after_fence,
                },
            }
        )
    return {
        "ranking": [s["seq"] for s in steps],
        "steps": steps,
        "conclusion": inv.conclusion,
        "repair_sites": list(inv.repair_sites),
        "unsupported": list(inv.unsupported),
        "replays_used": inv.replays_used,
        "notes": list(inv.notes),
    }


@dataclass(frozen=True)
class InstanceResult:
    instance_id: str
    data: dict[str, Any]  # JSON-pure, label-free


def evaluate_instance(
    instance: dict[str, Any],
    ctx: ReplayContext,
    methods: Sequence[str],
    *,
    authorization: HeldOutAuthorization | None = None,
) -> InstanceResult:
    record = record_instance(instance, authorization=authorization)
    replay = replay_strict(record, ctx)
    trace = record.observable()
    flags = support_flags(trace)
    ordered, symptom, _chain = b3_order(trace, flags)
    runners: dict[str, Callable[[], Investigation]] = {
        "B1": lambda: rank_b1(trace, flags),
        "B3": lambda: rank_b3(trace, flags),
        "B4": lambda: rank_b4(InterventionService(record, ctx), flags),
        "CF": lambda: rank_cf(InterventionService(record, ctx), flags),
    }
    data = {
        "instance_id": instance["instance_id"],
        "scenario_id": instance["scenario_id"],
        "split": instance["split"],
        "kind": instance["kind"],
        "original_outcome": record.footer.outcome.outcome.value,
        "replay_verdict": replay.verdict.value,
        "symptom_seq": symptom,
        "candidates": sorted(e.seq for e in ordered),
        "steps": {
            str(e.seq): {"boundary": e.boundary.value, "name": e.name, "step_index": e.step_index}
            for e in trace.events
            if e.boundary.value in ("DECISION", "TOOL")
        },
        "flags": {str(k): list(v) for k, v in sorted(flags.items())},
        "methods": {m: _investigation_json(runners[m]()) for m in methods},
    }
    return InstanceResult(instance["instance_id"], data)


def regression_check(
    instance: dict[str, Any],
    ctx: ReplayContext,
    *,
    authorization: HeldOutAuthorization | None = None,
) -> dict[str, Any] | None:
    """For instances with environment faults: candidate v2 regression must build no cassette."""
    require_authorization(instance["split"], authorization)
    plan = instance["fault_plan"]
    if not plan or not any(f["stage"] != FaultStage.DECISION.value for f in plan["faults"]):
        return None
    record = record_instance(instance, authorization=authorization)
    before = Cassette.constructed
    report = run_regression(
        record.header, record.fault_plan, record.footer.outcome.outcome, ctx, policy_version="v2"
    )
    return {
        "instance_id": instance["instance_id"],
        "baseline_outcome": record.footer.outcome.outcome.value,
        "verdict": report.verdict.value,
        "comparison": report.comparison.value,
        "passes": report.passes,
        "n": report.n,
        "cassettes_constructed": Cassette.constructed - before,
    }


def evaluate_split(
    instances: Sequence[dict[str, Any]],
    split: str,
    ctx: ReplayContext,
    methods: Sequence[str] = METHODS,
    *,
    authorization: HeldOutAuthorization | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (label-free instance results, regression checks) for ``split`` only."""
    require_authorization(split, authorization)
    chosen = [i for i in instances if i["split"] == split]
    auth = authorization
    results = [evaluate_instance(i, ctx, methods, authorization=auth).data for i in chosen]
    regressions = [
        r for i in chosen if (r := regression_check(i, ctx, authorization=auth)) is not None
    ]
    return results, regressions
