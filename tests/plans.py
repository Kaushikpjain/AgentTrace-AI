"""Builders for small, serializable FaultPlans used across tests."""

from __future__ import annotations

from typing import Any

from agenttrace.runtime.types import Decision
from agenttrace.trace.canonical import to_json_value
from agenttrace.trace.schema import Boundary, FaultPlan, FaultSpec, FaultStage, FaultTrigger


def _tool_fault(
    operator: str, stage: FaultStage, tool: str, occurrence: int, params: dict[str, Any]
) -> FaultSpec:
    return FaultSpec(
        fault_id=f"{operator.lower()}-{tool}-{occurrence}",
        operator=operator,
        stage=stage,
        trigger=FaultTrigger(boundary=Boundary.TOOL, name=tool, occurrence=occurrence),
        params=params,
    )


def lost_ack(tool: str = "issue_refund", occurrence: int = 1) -> FaultPlan:
    return FaultPlan(
        plan_id="lost-ack",
        faults=(_tool_fault("LOST_ACK", FaultStage.POST_EXECUTION, tool, occurrence, {}),),
    )


def pre_execution_timeout(tool: str = "issue_refund", occurrence: int = 1) -> FaultPlan:
    return FaultPlan(
        plan_id="pre-execution-timeout",
        faults=(
            _tool_fault("TIMEOUT_BEFORE_EXECUTION", FaultStage.PRE_EXECUTION, tool, occurrence, {}),
        ),
    )


def corrupt_output(tool: str, path: list[Any], value: Any, occurrence: int = 1) -> FaultPlan:
    return FaultPlan(
        plan_id="corrupt-output",
        faults=(
            _tool_fault(
                "CORRUPT_OUTPUT",
                FaultStage.POST_EXECUTION,
                tool,
                occurrence,
                {"path": path, "value": value},
            ),
        ),
    )


def replace_decision(occurrence: int, decision: Decision) -> FaultPlan:
    return FaultPlan(
        plan_id="replace-decision",
        faults=(
            FaultSpec(
                fault_id=f"replace-decision-{occurrence}",
                operator="REPLACE_DECISION",
                stage=FaultStage.DECISION,
                trigger=FaultTrigger(boundary=Boundary.DECISION, occurrence=occurrence),
                params={"decision": to_json_value(decision)},
            ),
        ),
    )


def _decision_fault(
    operator: str, occurrence: int, params: dict[str, Any], fault_id: str | None = None
) -> FaultSpec:
    return FaultSpec(
        fault_id=fault_id or f"{operator.lower()}-d{occurrence}",
        operator=operator,
        stage=FaultStage.DECISION,
        trigger=FaultTrigger(boundary=Boundary.DECISION, occurrence=occurrence),
        params=params,
    )


def archived_policy_doc(scenario_id: str = "T1") -> dict[str, Any]:
    from agenttrace.env.support.scenario import load_scenario

    doc = load_scenario(scenario_id).initial_state.policy_docs["POL-REFUND-2019"]
    data = to_json_value(doc)
    assert isinstance(data, dict)
    return data


def wrong_retrieval(scenario_id: str = "T1", occurrence: int = 1) -> FaultPlan:
    return FaultPlan(
        plan_id="wrong-retrieval",
        faults=(
            _tool_fault(
                "WRONG_RETRIEVAL",
                FaultStage.POST_EXECUTION,
                "search_policy",
                occurrence,
                {"data": archived_policy_doc(scenario_id)},
            ),
        ),
    )


def wrong_tool(occurrence: int, tool: str, args: dict[str, Any]) -> FaultPlan:
    return FaultPlan(
        plan_id="wrong-tool",
        faults=(_decision_fault("WRONG_TOOL", occurrence, {"tool": tool, "args": args}),),
    )


def wrong_argument(
    occurrence: int, tool: str, arg: str, mode: str = "drop", value: Any = None
) -> FaultPlan:
    params: dict[str, Any] = {"tool": tool, "arg": arg, "mode": mode}
    if mode == "replace":
        params["value"] = value
    return FaultPlan(
        plan_id="wrong-argument", faults=(_decision_fault("WRONG_ARGUMENT", occurrence, params),)
    )


def decoy(occurrence: int = 2, customer_id: str = "C1") -> FaultSpec:
    return _decision_fault(
        "DECOY_READ",
        occurrence,
        {"tool": "get_customer", "args": {"customer_id": customer_id}},
        fault_id=f"decoy-d{occurrence}",
    )


def combine(plan_id: str, *plans_or_specs: FaultPlan | FaultSpec) -> FaultPlan:
    specs: list[FaultSpec] = []
    for item in plans_or_specs:
        specs.extend(item.faults if isinstance(item, FaultPlan) else (item,))
    return FaultPlan(plan_id=plan_id, faults=tuple(specs))
