from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agenttrace.env.support.scenario import load_scenario
from agenttrace.faults import OPERATORS, FaultPlanError, PlanFaultHook, validate_plan
from agenttrace.runner import record_scenario
from agenttrace.runtime.faults import DecisionContext, ToolContext
from agenttrace.runtime.types import Decision, ToolResponse
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    Boundary,
    EventStatus,
    FaultEffect,
    FaultPlan,
    FaultSpec,
    FaultStage,
    FaultTrigger,
    Outcome,
)
from agenttrace.trace.store import (
    CorruptTraceError,
    JsonlTraceStore,
    TraceIntegrityError,
)
from tests import plans

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "fault_plans"


def _ctx(tool: str = "issue_refund", occurrence: int = 1) -> ToolContext:
    return ToolContext(seq=3, step_index=1, tool=tool, args={}, occurrence=occurrence, attempt=1)


def test_every_operator_declares_one_stage() -> None:
    assert set(OPERATORS) == {
        "TIMEOUT_BEFORE_EXECUTION",
        "LOST_ACK",
        "CORRUPT_OUTPUT",
        "REPLACE_DECISION",
        "WRONG_TOOL",
        "WRONG_ARGUMENT",
        "WRONG_RETRIEVAL",
        "DECOY_READ",
    }
    for op in OPERATORS.values():
        assert isinstance(op.stage, FaultStage)
        assert (op.tool_fn is None) != (op.decision_fn is None)
        assert (op.decision_fn is not None) == (op.stage is FaultStage.DECISION)


def test_trigger_and_spec_validation() -> None:
    with pytest.raises(ValidationError, match="tool name"):
        FaultTrigger(boundary=Boundary.TOOL, occurrence=1)
    with pytest.raises(ValidationError, match="no name"):
        FaultTrigger(boundary=Boundary.DECISION, name="x", occurrence=1)
    with pytest.raises(ValidationError):
        FaultTrigger(boundary=Boundary.TOOL, name="x", occurrence=0)
    with pytest.raises(ValidationError, match="DECISION-stage"):
        FaultSpec(
            fault_id="f",
            operator="LOST_ACK",
            stage=FaultStage.DECISION,
            trigger=FaultTrigger(boundary=Boundary.TOOL, name="x", occurrence=1),
        )


def test_plan_rejects_duplicate_ids_and_bad_schema() -> None:
    spec = plans.lost_ack().faults[0]
    with pytest.raises(ValidationError, match="unique"):
        FaultPlan(plan_id="p", faults=(spec, spec))
    with pytest.raises(ValidationError, match="unsupported"):
        FaultPlan(schema_version="2.0", plan_id="p")


@pytest.mark.parametrize(
    ("operator", "stage", "params", "match"),
    [
        ("BOGUS", FaultStage.POST_EXECUTION, {}, "unknown operator"),
        ("LOST_ACK", FaultStage.PRE_EXECUTION, {}, "has stage"),
        ("LOST_ACK", FaultStage.POST_EXECUTION, {"x": 1}, "unknown params"),
        ("CORRUPT_OUTPUT", FaultStage.POST_EXECUTION, {"path": []}, "non-empty"),
        ("CORRUPT_OUTPUT", FaultStage.POST_EXECUTION, {"path": ["data"]}, "value"),
    ],
)
def test_validate_plan_errors(operator: str, stage: FaultStage, params: dict, match: str) -> None:  # type: ignore[type-arg]
    plan = FaultPlan(
        plan_id="p",
        faults=(
            FaultSpec(
                fault_id="f",
                operator=operator,
                stage=stage,
                params=params,
                trigger=FaultTrigger(boundary=Boundary.TOOL, name="t", occurrence=1),
            ),
        ),
    )
    with pytest.raises(FaultPlanError, match=match):
        validate_plan(plan)
    with pytest.raises(FaultPlanError):
        PlanFaultHook(plan)


def test_replace_decision_requires_valid_decision() -> None:
    plan = FaultPlan(
        plan_id="p",
        faults=(
            FaultSpec(
                fault_id="d",
                operator="REPLACE_DECISION",
                stage=FaultStage.DECISION,
                trigger=FaultTrigger(boundary=Boundary.DECISION, occurrence=1),
                params={"decision": {"kind": "tool_call"}},
            ),
        ),
    )
    with pytest.raises(FaultPlanError, match="valid 'decision'"):
        validate_plan(plan)


def test_hook_fires_only_on_matching_occurrence() -> None:
    hook = PlanFaultHook(plans.lost_ack(occurrence=2))
    ok = ToolResponse.ok({"refund_id": "R-0001"})
    assert hook.post_execution(_ctx(occurrence=1), ok) == (ok, [])
    assert hook.post_execution(_ctx(tool="get_order", occurrence=2), ok) == (ok, [])
    delivered, applied = hook.post_execution(_ctx(occurrence=2), ok)
    assert delivered.status is EventStatus.TIMEOUT
    assert applied[0].effect is FaultEffect.TRANSFORMED_OUTPUT
    assert applied[0].input_fp == fingerprint(ok)


def test_pre_execution_hook() -> None:
    hook = PlanFaultHook(plans.pre_execution_timeout())
    prevented, applied = hook.pre_execution(_ctx())
    assert prevented is not None and prevented.status is EventStatus.TIMEOUT
    assert applied[0].effect is FaultEffect.PREVENTED_EXECUTION
    assert hook.pre_execution(_ctx(occurrence=2)) == (None, [])


def test_corrupt_output_absent_path_is_noop() -> None:
    hook = PlanFaultHook(plans.corrupt_output("get_order", ["data", "nope", "x"], "1"))
    response = ToolResponse.ok({"total": "80"})
    assert hook.post_execution(_ctx(tool="get_order"), response) == (response, [])
    hook = PlanFaultHook(plans.corrupt_output("get_order", ["data", "total"], "800.00"))
    delivered, applied = hook.post_execution(_ctx(tool="get_order"), response)
    assert delivered.data == {"total": "800.00"} and len(applied) == 1  # strings kept verbatim


def test_corrupt_output_list_index() -> None:
    hook = PlanFaultHook(plans.corrupt_output("get_order", ["data", "items", 0, "sku"], "X"))
    response = ToolResponse.ok({"items": [{"sku": "A"}]})
    delivered, _ = hook.post_execution(_ctx(tool="get_order"), response)
    assert delivered.data == {"items": [{"sku": "X"}]}
    assert hook.post_execution(_ctx(tool="get_order"), ToolResponse.ok({"items": []}))[1] == []


def test_decision_hook() -> None:
    target = Decision.call("close_ticket", ticket_id="TK1", resolution="DENIED")
    hook = PlanFaultHook(plans.replace_decision(2, target))
    raw = Decision.call("get_order", order_id="O1")
    ctx1 = DecisionContext(seq=1, step_index=0, occurrence=1)
    assert hook.on_decision(ctx1, raw) == (raw, [])
    delivered, applied = hook.on_decision(DecisionContext(seq=4, step_index=1, occurrence=2), raw)
    assert delivered == target and applied[0].stage is FaultStage.DECISION


def test_fault_plan_hash_is_recorded_and_stable() -> None:
    record = record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack())
    assert record.fault_plan == plans.lost_ack()
    assert record.header.fault_plan_hash == fingerprint(plans.lost_ack())
    assert record.observable().model_dump().keys() == {"header", "events", "footer"}


def test_fault_plan_roundtrips_through_store(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    record = record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack())
    store.save(record)
    run_id = record.header.run_id
    assert (tmp_path / run_id / "fault_plan.json").is_file()
    assert store.load_fault_plan(run_id) == plans.lost_ack()
    assert store.load_record(run_id) == record


def test_missing_fault_plan_file_is_corruption(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    record = record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack())
    store.save(record)
    (tmp_path / record.header.run_id / "fault_plan.json").unlink()
    with pytest.raises(CorruptTraceError, match="fault_plan"):
        store.load_record(record.header.run_id)


def test_tampered_fault_plan_file_is_integrity_error(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    record = record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack())
    store.save(record)
    path = tmp_path / record.header.run_id / "fault_plan.json"
    data = json.loads(path.read_text())
    data["faults"][0]["trigger"]["occurrence"] = 2
    path.write_text(json.dumps(data))
    with pytest.raises(TraceIntegrityError, match="does not match header"):
        store.load_record(record.header.run_id)


def test_unexpected_fault_plan_file_is_integrity_error(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    record = record_scenario(load_scenario("T1"))
    store.save(record)
    (tmp_path / record.header.run_id / "fault_plan.json").write_text("{}")
    with pytest.raises(TraceIntegrityError, match="unexpected"):
        store.load_record(record.header.run_id)


@pytest.mark.parametrize(
    ("name", "outcome"),
    [
        ("lost_ack_refund.json", Outcome.FAIL),
        ("timeout_before_refund.json", Outcome.PASS),
        ("corrupt_order_total.json", Outcome.FAIL),
    ],
)
def test_example_fault_plans_are_valid(name: str, outcome: Outcome) -> None:
    plan = FaultPlan.model_validate(json.loads((EXAMPLES / name).read_text()))
    validate_plan(plan)
    record = record_scenario(load_scenario("T1"), fault_plan=plan)
    assert record.footer.outcome.outcome is outcome
