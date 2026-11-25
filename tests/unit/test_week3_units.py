"""Unit tests: Week 3 fault operators, validators, localizers and leakage guards."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agenttrace.env.support.scenario import load_scenario
from agenttrace.evals.validators import (
    FLAG_ARCHIVED_POLICY,
    FLAG_INVALID_ARGUMENTS,
    FLAG_OUTPUT_INCONSISTENT,
    FLAG_REFUND_OVER_LIMIT,
    FLAG_REPEATED_MUTATION,
    FLAG_TIMEOUT,
    FLAG_TIMEOUT_WITH_COMMIT,
    support_flags,
)
from agenttrace.faults import FaultPlanError, PlanFaultHook, validate_plan
from agenttrace.localize.baselines import (
    W_CHAIN,
    W_ERROR,
    W_FLAG,
    W_MUTATING,
    rank_b1,
    rank_b3,
    rank_b4,
)
from agenttrace.localize.counterfactual import rank_cf
from agenttrace.localize.observe import symptom_chain, symptom_seq, tool_index_at_or_after
from agenttrace.localize.report import render_markdown
from agenttrace.localize.types import NO_FAILURE, NOT_ISOLATED, EvidenceLabel
from agenttrace.replay.regression import environment_fixture, wilson_interval
from agenttrace.replay.service import InterventionService
from agenttrace.runner import record_scenario, support_replay_context
from agenttrace.runtime.faults import DecisionContext, ToolContext
from agenttrace.runtime.types import Decision, ToolResponse
from agenttrace.trace.schema import (
    Boundary,
    FaultPlan,
    FaultSpec,
    FaultStage,
    FaultTrigger,
    Outcome,
)
from tests import plans

CTX = support_replay_context()
SRC = Path(__file__).resolve().parents[2] / "src" / "agenttrace"
DCTX = DecisionContext(seq=4, step_index=1, occurrence=2)


# ------------------------------------------------------------------ operators
def test_wrong_tool_applies_only_to_a_different_tool() -> None:
    hook = PlanFaultHook(plans.wrong_tool(2, "close_ticket", {"ticket_id": "TK1"}))
    raw = Decision.call("get_order", order_id="O1")
    delivered, applied = hook.on_decision(DCTX, raw)
    assert delivered.tool == "close_ticket" and delivered.args == {"ticket_id": "TK1"}
    assert applied[0].stage is FaultStage.DECISION
    same = Decision.call("close_ticket", ticket_id="TK1")
    assert hook.on_decision(DCTX, same) == (same, [])
    assert hook.on_decision(DCTX, Decision.final()) == (Decision.final(), [])


@pytest.mark.parametrize(
    ("mode", "value", "expected"),
    [("drop", None, {"order_id": "O1"}), ("replace", "999", {"order_id": "O1", "amount": "999"})],
)
def test_wrong_argument(mode: str, value: str | None, expected: dict[str, str]) -> None:
    hook = PlanFaultHook(plans.wrong_argument(2, "issue_refund", "amount", mode, value))
    raw = Decision.call("issue_refund", order_id="O1", amount="80")
    delivered, applied = hook.on_decision(DCTX, raw)
    assert delivered.args == expected and len(applied) == 1
    other = Decision.call("get_order", order_id="O1")
    assert hook.on_decision(DCTX, other) == (other, [])  # different tool: no-op
    missing = Decision.call("issue_refund", order_id="O1")
    assert hook.on_decision(DCTX, missing) == (missing, [])  # argument absent: no-op


def test_wrong_argument_replace_same_value_is_noop() -> None:
    hook = PlanFaultHook(plans.wrong_argument(2, "get_order", "order_id", "replace", "O1"))
    raw = Decision.call("get_order", order_id="O1")
    assert hook.on_decision(DCTX, raw) == (raw, [])


def test_wrong_retrieval_only_on_ok_responses() -> None:
    hook = PlanFaultHook(plans.wrong_retrieval())
    ctx = ToolContext(seq=8, step_index=2, tool="search_policy", args={}, occurrence=1, attempt=1)
    ok = ToolResponse.ok({"doc_id": "POL-REFUND-STD"})
    delivered, applied = hook.post_execution(ctx, ok)
    assert delivered.data["doc_id"] == "POL-REFUND-2019" and applied  # type: ignore[index]
    error = ToolResponse.error_response("NOT_FOUND", "x")
    assert hook.post_execution(ctx, error) == (error, [])


def test_decoy_read() -> None:
    hook = PlanFaultHook(plans.combine("d", plans.decoy(2, "C1")))
    delivered, applied = hook.on_decision(DCTX, Decision.call("get_order", order_id="O1"))
    assert (delivered.tool, delivered.args, delivered.summary) == (
        "get_customer",
        {"customer_id": "C1"},
        "decoy",
    )
    assert applied[0].operator == "DECOY_READ"


@pytest.mark.parametrize(
    ("operator", "stage", "params", "match"),
    [
        ("WRONG_TOOL", FaultStage.DECISION, {"tool": "x"}, "args"),
        ("WRONG_TOOL", FaultStage.DECISION, {"tool": "x", "args": {}, "extra": 1}, "unknown"),
        ("WRONG_ARGUMENT", FaultStage.DECISION, {"tool": "x", "arg": "a", "mode": "zap"}, "mode"),
        (
            "WRONG_ARGUMENT",
            FaultStage.DECISION,
            {"tool": "x", "arg": "a", "mode": "replace"},
            "value",
        ),
        ("WRONG_RETRIEVAL", FaultStage.POST_EXECUTION, {"data": {}}, "non-empty"),
        ("DECOY_READ", FaultStage.DECISION, {"args": {}}, "tool"),
    ],
)
def test_new_operator_param_validation(
    operator: str, stage: FaultStage, params: dict, match: str
) -> None:  # type: ignore[type-arg]
    boundary = Boundary.DECISION if stage is FaultStage.DECISION else Boundary.TOOL
    trigger = FaultTrigger(
        boundary=boundary, name=None if boundary is Boundary.DECISION else "t", occurrence=1
    )
    plan = FaultPlan(
        plan_id="p",
        faults=(
            FaultSpec(fault_id="f", operator=operator, stage=stage, trigger=trigger, params=params),
        ),
    )
    with pytest.raises(FaultPlanError, match=match):
        validate_plan(plan)


# ------------------------------------------------------------------ validators and observe
def test_validators_flag_observable_problems() -> None:
    f3 = record_scenario(
        load_scenario("T1"),
        fault_plan=plans.corrupt_output("get_order", ["data", "total"], "800.00"),
    )
    flags = support_flags(f3.observable())
    get_order = next(e.seq for e in f3.events if e.name == "get_order")
    assert FLAG_OUTPUT_INCONSISTENT in flags[get_order]

    f4 = record_scenario(load_scenario("T8"), fault_plan=plans.wrong_retrieval("T8"))
    flags = support_flags(f4.observable())
    assert (
        FLAG_ARCHIVED_POLICY in flags[next(e.seq for e in f4.events if e.name == "search_policy")]
    )

    f5 = record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack())
    flags = support_flags(f5.observable())
    first, second = [e.seq for e in f5.events if e.name == "issue_refund"]
    assert {FLAG_TIMEOUT, FLAG_TIMEOUT_WITH_COMMIT} <= set(flags[first])
    assert FLAG_REPEATED_MUTATION in flags[second]

    f2 = record_scenario(
        load_scenario("T1"), fault_plan=plans.wrong_argument(4, "issue_refund", "amount")
    )
    flags = support_flags(f2.observable())
    assert (
        FLAG_INVALID_ARGUMENTS in flags[next(e.seq for e in f2.events if e.name == "issue_refund")]
    )

    over = record_scenario(
        load_scenario("T1"),
        fault_plan=plans.wrong_argument(4, "issue_refund", "amount", "replace", "99.00"),
    )
    assert FLAG_REFUND_OVER_LIMIT not in sum(support_flags(over.observable()).values(), ())
    clean = record_scenario(load_scenario("T1"))
    assert support_flags(clean.observable()) == {}


def test_validator_refund_over_observed_limit() -> None:
    plan = plans.combine(
        "p",
        plans.wrong_retrieval(),
        plans.wrong_tool(4, "issue_refund", {"order_id": "O1", "amount": "80"}),
    )
    record = record_scenario(load_scenario("T1"), fault_plan=plan)
    flags = support_flags(record.observable())
    refund = next(e.seq for e in record.events if e.name == "issue_refund")
    assert FLAG_REFUND_OVER_LIMIT in flags[refund]  # 80 > archived limit 50


def test_symptom_and_chain() -> None:
    record = record_scenario(
        load_scenario("T1"),
        fault_plan=plans.corrupt_output("get_order", ["data", "total"], "800.00"),
    )
    trace = record.observable()
    symptom = symptom_seq(trace)
    assert next(e for e in trace.events if e.seq == symptom).name == "close_ticket"
    chain = symptom_chain(trace, symptom)
    names = {e.name for e in trace.events if e.seq in chain}
    assert names == {"close_ticket", "decide"}  # ticket args come from the task, not from reads
    clean = record_scenario(load_scenario("T1")).observable()
    refund = next(e.seq for e in clean.events if e.name == "issue_refund")
    refund_chain = {e.name for e in clean.events if e.seq in symptom_chain(clean, refund)}
    assert {"issue_refund", "decide", "get_order"} <= refund_chain  # order_id/amount from get_order
    assert tool_index_at_or_after(trace, 0) == 0 and tool_index_at_or_after(trace, 10**6) is None


def test_b3_weights_are_fixed_and_documented() -> None:
    assert (W_CHAIN, W_FLAG, W_ERROR, W_MUTATING) == (2, 3, 1, 1)


def test_localizers_on_delayed_effect_failure() -> None:
    record = record_scenario(
        load_scenario("T1"),
        fault_plan=plans.corrupt_output("get_order", ["data", "total"], "800.00"),
    )
    trace, flags = record.observable(), support_flags(record.observable())
    get_order = next(e.seq for e in record.events if e.name == "get_order")
    b1, b3 = rank_b1(trace, flags), rank_b3(trace, flags)
    assert b1.top is not None and b1.top.seq == get_order  # visible via OUTPUT_INCONSISTENT
    assert b3.top is not None and all(s.label is EvidenceLabel.SUSPICION for s in b3.ranking)
    cf = rank_cf(InterventionService(record, CTX), flags)
    assert cf.repair_sites == (get_order,) and cf.top is not None
    assert cf.top.label is EvidenceLabel.INTERVENTIONAL_REPAIR
    assert cf.top.experiment is not None and cf.top.experiment.placebo_valid
    assert cf.replays_used > 0 and cf.rank_of(get_order) == 1


def test_cf_reports_not_isolated_and_unsupported() -> None:
    plan = plans.combine(
        "multi",
        plans.wrong_argument(2, "get_order", "order_id", "replace", "O6A"),
        plans.wrong_retrieval("T6"),
    )
    record = record_scenario(load_scenario("T6"), fault_plan=plan)
    cf = rank_cf(InterventionService(record, CTX), support_flags(record.observable()))
    assert cf.conclusion == NOT_ISOLATED and not cf.repair_sites
    deviations = [s for s in cf.ranking if s.label is EvidenceLabel.REFERENCE_DEVIATION]
    assert len(deviations) >= 2


def test_cf_on_passing_run_notes_no_repair_possible() -> None:
    record = record_scenario(load_scenario("T1"))
    cf = rank_cf(InterventionService(record, CTX), {})
    assert cf.notes and not cf.repair_sites
    assert all(s.label is EvidenceLabel.SUSPICION for s in cf.ranking)  # all consistent
    assert cf.conclusion == NO_FAILURE  # not NOT_ISOLATED: nothing failed (ADR-025)


def test_b4_is_fooled_by_decoy_cf_is_not() -> None:
    plan = plans.combine("d1+f4", plans.decoy(2, "C1"), plans.wrong_retrieval())
    record = record_scenario(load_scenario("T1"), fault_plan=plan)
    flags = support_flags(record.observable())
    retrieval = next(e.seq for e in record.events if e.name == "search_policy")
    b4 = rank_b4(InterventionService(record, CTX), flags)
    cf = rank_cf(InterventionService(record, CTX), flags)
    assert b4.top is not None and b4.top.name == "decide"  # the decoy decision
    assert cf.top is not None and cf.top.seq == retrieval
    markdown = render_markdown(record.observable(), [b4, cf])
    assert "INTERVENTIONAL_REPAIR" in markdown and "not proof of a unique cause" in markdown


def test_service_exposes_no_privileged_data() -> None:
    record = record_scenario(load_scenario("T1"), fault_plan=plans.wrong_retrieval())
    service = InterventionService(record, CTX)
    public = {name for name in dir(service) if not name.startswith("_")}
    assert public == {"trace", "reference_deviation", "experiment", "replays_used"}
    assert set(type(service.trace).model_fields) == {"header", "events", "footer"}
    summary = service.experiment(next(e.seq for e in record.events if e.name == "search_policy"))
    assert summary.interventional_repair and service.replays_used == 2
    assert not hasattr(summary, "run")


# ------------------------------------------------------------------ regression helpers
def test_environment_fixture_and_wilson() -> None:
    plan = plans.combine("p", plans.lost_ack(), plans.wrong_tool(2, "x", {}))
    fixture, dropped = environment_fixture(plan)
    assert fixture is not None and [f.operator for f in fixture.faults] == ["LOST_ACK"]
    assert dropped == ("wrong_tool-d2",)
    assert environment_fixture(None) == (None, ())
    low, high = wilson_interval(2, 2)
    assert 0.3 < low < 0.4 and high == 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)


# ------------------------------------------------------------------ leakage guards (C3)
FORBIDDEN_MODULES = (
    "agenttrace.bench",
    "agenttrace.trace.store",
    "agenttrace.faults",
    "agenttrace.runner",
)
FORBIDDEN_NAMES = {
    "load_ledger",
    "load_record",
    "load_fault_plan",
    "load_labels",
    "INJECTION_CLEAN_VALUE",
    "ledger",
    "fault_plan",
    "allow_privileged",
}


@pytest.mark.parametrize("path", sorted((SRC / "localize").glob("*.py")), ids=lambda p: p.name)
def test_localizers_cannot_reach_privileged_data(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith(FORBIDDEN_MODULES), f"{path.name}: {node.module}"
            imported = {alias.name for alias in node.names}
            assert not imported & FORBIDDEN_NAMES, f"{path.name}: {imported & FORBIDDEN_NAMES}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(FORBIDDEN_MODULES)
        if isinstance(node, ast.Attribute):
            assert node.attr not in FORBIDDEN_NAMES, f"{path.name}: .{node.attr}"
            assert "__record" not in node.attr
        if isinstance(node, ast.Name):
            assert node.id not in {"INJECTION_CLEAN_VALUE"}


def test_localizer_signatures_take_only_observable_inputs() -> None:
    import inspect

    for fn in (rank_b1, rank_b3):
        params = list(inspect.signature(fn).parameters)
        assert params == ["trace", "flags"]
    for fn in (rank_b4, rank_cf):
        assert list(inspect.signature(fn).parameters) == ["service", "flags"]
    assert Outcome.PASS  # keep import used
