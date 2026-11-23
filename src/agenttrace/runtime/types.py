"""Runtime value types and the Policy protocol (shared by runtime and policies)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, model_validator

from agenttrace.trace.canonical import JsonValue
from agenttrace.trace.schema import EventStatus, JsonPayload


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Decision(_Frozen):
    """A policy decision: call one tool, or finish."""

    kind: Literal["tool_call", "final"]
    tool: str | None = None
    args: JsonPayload = None
    summary: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind == "tool_call":
            if not self.tool:
                raise ValueError("tool_call decisions require a tool name")
            if not isinstance(self.args, dict):
                raise ValueError("tool_call decisions require an args object")
        elif self.tool is not None or self.args is not None:
            raise ValueError("final decisions carry no tool or args")
        return self

    @staticmethod
    def call(tool: str, summary: str | None = None, **args: Any) -> Decision:
        return Decision(kind="tool_call", tool=tool, args=args, summary=summary)

    @staticmethod
    def final(summary: str | None = None) -> Decision:
        return Decision(kind="final", summary=summary)


class ToolError(_Frozen):
    code: str
    message: str


class ToolResponse(_Frozen):
    """What the agent observes from a tool call (the *delivered* response)."""

    status: EventStatus
    data: JsonPayload = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.status is EventStatus.OK and self.error is not None:
            raise ValueError("OK responses carry no error")
        if self.status is not EventStatus.OK and self.error is None:
            raise ValueError("ERROR/TIMEOUT responses require an error")
        return self

    @staticmethod
    def ok(data: dict[str, JsonValue] | None) -> ToolResponse:
        return ToolResponse(status=EventStatus.OK, data=data)

    @staticmethod
    def error_response(code: str, message: str) -> ToolResponse:
        return ToolResponse(status=EventStatus.ERROR, error=ToolError(code=code, message=message))

    @staticmethod
    def timeout(message: str = "tool call timed out") -> ToolResponse:
        return ToolResponse(
            status=EventStatus.TIMEOUT, error=ToolError(code="TIMEOUT", message=message)
        )


class Observation(_Frozen):
    """One entry of the agent's history: a tool call and the response it observed."""

    seq: int
    tool: str
    args: JsonPayload
    response: ToolResponse


class Policy[T: BaseModel](Protocol):
    """A decision-maker behind the DECISION boundary (scripted now; LLM-backed later)."""

    @property
    def policy_id(self) -> str: ...

    @property
    def policy_version(self) -> str: ...

    @property
    def source_hash(self) -> str: ...

    @property
    def deterministic(self) -> bool: ...

    def decide(self, task: T, history: Sequence[Observation]) -> Decision: ...
