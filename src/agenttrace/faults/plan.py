"""PlanFaultHook: applies a serializable FaultPlan through the gateway's fault-hook seam.

Stateless: matching uses only the gateway-provided context (tool occurrence / decision
occurrence), so the same plan behaves identically in RECORD and REPLAY_STRICT.
"""

from __future__ import annotations

from typing import Any

from agenttrace.faults.operators import OPERATORS, FaultPlanError
from agenttrace.runtime.faults import DecisionContext, ToolContext
from agenttrace.runtime.types import Decision, ToolResponse
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    Boundary,
    FaultApplication,
    FaultEffect,
    FaultPlan,
    FaultSpec,
    FaultStage,
)


def validate_plan(plan: FaultPlan) -> None:
    """Raise FaultPlanError unless every fault uses a registered operator correctly."""
    for spec in plan.faults:
        op = OPERATORS.get(spec.operator)
        if op is None:
            raise FaultPlanError(f"{spec.fault_id}: unknown operator {spec.operator!r}")
        if op.stage is not spec.stage:
            raise FaultPlanError(
                f"{spec.fault_id}: operator {spec.operator} has stage {op.stage}, "
                f"plan declares {spec.stage}"
            )
        assert isinstance(spec.params, dict)
        op.validate(spec.params)


class PlanFaultHook:
    def __init__(self, plan: FaultPlan) -> None:
        validate_plan(plan)
        self._plan = plan
        self._hash = fingerprint(plan)

    @property
    def plan(self) -> FaultPlan:
        return self._plan

    @property
    def fault_plan_hash(self) -> str | None:
        return self._hash

    def _tool_specs(self, stage: FaultStage, ctx: ToolContext) -> list[FaultSpec]:
        return [
            s
            for s in self._plan.faults
            if s.stage is stage
            and s.trigger.boundary is Boundary.TOOL
            and s.trigger.name == ctx.tool
            and s.trigger.occurrence == ctx.occurrence
        ]

    @staticmethod
    def _params(spec: FaultSpec) -> dict[str, Any]:
        assert isinstance(spec.params, dict)
        return spec.params

    def on_decision(
        self, ctx: DecisionContext, decision: Decision
    ) -> tuple[Decision, list[FaultApplication]]:
        applications: list[FaultApplication] = []
        for spec in self._plan.faults:
            if spec.stage is not FaultStage.DECISION or spec.trigger.occurrence != ctx.occurrence:
                continue
            fn = OPERATORS[spec.operator].decision_fn
            assert fn is not None
            new = fn(self._params(spec), decision)
            applications.append(
                FaultApplication(
                    fault_id=spec.fault_id,
                    operator=spec.operator,
                    stage=spec.stage,
                    effect=FaultEffect.TRANSFORMED_OUTPUT,
                    input_fp=fingerprint(decision),
                    output_fp=fingerprint(new),
                )
            )
            decision = new
        return decision, applications

    def pre_execution(self, ctx: ToolContext) -> tuple[ToolResponse | None, list[FaultApplication]]:
        for spec in self._tool_specs(FaultStage.PRE_EXECUTION, ctx):
            fn = OPERATORS[spec.operator].tool_fn
            assert fn is not None
            out = fn(self._params(spec), None)
            if out is not None:  # first preventing fault wins
                return out, [
                    FaultApplication(
                        fault_id=spec.fault_id,
                        operator=spec.operator,
                        stage=spec.stage,
                        effect=FaultEffect.PREVENTED_EXECUTION,
                        output_fp=fingerprint(out),
                    )
                ]
        return None, []

    def post_execution(
        self, ctx: ToolContext, response: ToolResponse
    ) -> tuple[ToolResponse, list[FaultApplication]]:
        applications: list[FaultApplication] = []
        for spec in self._tool_specs(FaultStage.POST_EXECUTION, ctx):
            fn = OPERATORS[spec.operator].tool_fn
            assert fn is not None
            out = fn(self._params(spec), response)
            if out is None:  # e.g. CORRUPT_OUTPUT path absent: nothing applied
                continue
            applications.append(
                FaultApplication(
                    fault_id=spec.fault_id,
                    operator=spec.operator,
                    stage=spec.stage,
                    effect=FaultEffect.TRANSFORMED_OUTPUT,
                    input_fp=fingerprint(response),
                    output_fp=fingerprint(out),
                )
            )
            response = out
        return response, applications
