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
