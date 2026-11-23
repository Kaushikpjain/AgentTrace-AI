"""Fault-hook seam (REPLAY_SPEC sections 3-4).

Week 1 ships only the protocol and a no-op hook. Concrete, stage-declared fault operators
and FaultPlans arrive in Week 3. A hook must be a deterministic function of its inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agenttrace.runtime.types import Decision, ToolResponse
from agenttrace.trace.canonical import JsonValue
from agenttrace.trace.schema import FaultApplication


@dataclass(frozen=True)
class DecisionContext:
    seq: int
    step_index: int


@dataclass(frozen=True)
class ToolContext:
    seq: int
    step_index: int
    tool: str
    args: JsonValue
    occurrence: int  # 1-based count of calls to this tool in the run
    attempt: int  # 1-based count of identical requests in the run


class FaultHook(Protocol):
    @property
    def fault_plan_hash(self) -> str | None:
        """Opaque hash of the fault plan (recorded in the header); None = no faults."""
        ...

    def on_decision(
        self, ctx: DecisionContext, decision: Decision
    ) -> tuple[Decision, list[FaultApplication]]:
        """DECISION stage: may transform the raw decision."""
        ...

    def pre_execution(self, ctx: ToolContext) -> tuple[ToolResponse | None, list[FaultApplication]]:
        """PRE_EXECUTION stage: return a response to PREVENT execution, or None to proceed."""
        ...

    def post_execution(
        self, ctx: ToolContext, response: ToolResponse
    ) -> tuple[ToolResponse, list[FaultApplication]]:
        """POST_EXECUTION stage: may transform the response; never the state transition."""
        ...


class NoFaults:
    """The default hook: applies nothing."""

    @property
    def fault_plan_hash(self) -> str | None:
        return None

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
