"""Test-only fault hooks exercising the lifecycle stages (not the Week 3 fault operators)."""

from __future__ import annotations

from collections.abc import Callable

from agenttrace.runtime.faults import DecisionContext, ToolContext
from agenttrace.runtime.types import Decision, ToolResponse
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import FaultApplication, FaultEffect, FaultStage


class _Base:
    @property
    def fault_plan_hash(self) -> str | None:
        return fingerprint({"test_hook": type(self).__name__})

    def on_decision(
        self, ctx: DecisionContext, decision: Decision
    ) -> tuple[Decision, list[FaultApplication]]:
        return decision, []

    def pre_execution(self, ctx: ToolContext) -> tuple[ToolResponse | None, list[FaultApplication]]:
        return None, []

    def post_execution(
        self, ctx: ToolContext, response: ToolResponse
    ) -> tuple[ToolResponse, list[FaultApplication]]:
        return response, []


class PreExecutionTimeout(_Base):
    """T0: the first call to ``tool`` times out BEFORE executing (no commit)."""

    def __init__(self, tool: str, occurrence: int = 1) -> None:
        self.tool, self.occurrence = tool, occurrence

    def pre_execution(self, ctx: ToolContext) -> tuple[ToolResponse | None, list[FaultApplication]]:
        if ctx.tool == self.tool and ctx.occurrence == self.occurrence:
            out = ToolResponse.timeout("injected timeout before execution")
            return out, [
                FaultApplication(
                    fault_id="t0",
                    operator="T0",
                    stage=FaultStage.PRE_EXECUTION,
                    effect=FaultEffect.PREVENTED_EXECUTION,
                    output_fp=fingerprint(out),
                )
            ]
        return None, []


class LostAck(_Base):
    """F5-like: ``tool`` executes and commits, but the agent receives a timeout."""

    def __init__(self, tool: str, occurrence: int = 1) -> None:
        self.tool, self.occurrence = tool, occurrence

    def post_execution(
        self, ctx: ToolContext, response: ToolResponse
    ) -> tuple[ToolResponse, list[FaultApplication]]:
        if ctx.tool == self.tool and ctx.occurrence == self.occurrence:
            out = ToolResponse.timeout("injected lost acknowledgement")
            return out, [
                FaultApplication(
                    fault_id="f5",
                    operator="F5",
                    stage=FaultStage.POST_EXECUTION,
                    effect=FaultEffect.TRANSFORMED_OUTPUT,
                    input_fp=fingerprint(response),
                    output_fp=fingerprint(out),
                )
            ]
        return response, []


class RewriteDecision(_Base):
    """DECISION stage: rewrite the decision at a given decision count."""

    def __init__(self, nth: int, rewrite: Callable[[Decision], Decision]) -> None:
        self.nth, self.rewrite, self._count = nth, rewrite, 0

    def on_decision(
        self, ctx: DecisionContext, decision: Decision
    ) -> tuple[Decision, list[FaultApplication]]:
        self._count += 1
        if self._count != self.nth:
            return decision, []
        out = self.rewrite(decision)
        return out, [
            FaultApplication(
                fault_id="d",
                operator="TEST_DECISION",
                stage=FaultStage.DECISION,
                effect=FaultEffect.TRANSFORMED_OUTPUT,
                input_fp=fingerprint(decision),
                output_fp=fingerprint(out),
            )
        ]
