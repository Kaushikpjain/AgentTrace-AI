"""Registered, stage-declared fault operators (TRACE_SCHEMA.md section 3.1).

Every operator declares exactly one FaultStage. Operators are pure functions of their
params and input; they never touch environment state (state transitions are decided by
the gateway, REPLAY_SPEC S4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agenttrace.runtime.types import Decision, ToolResponse
from agenttrace.trace.canonical import to_json_value
from agenttrace.trace.schema import EventStatus, FaultStage


class FaultPlanError(ValueError):
    """A fault plan references an unknown operator, a wrong stage or invalid params."""


_MISSING = object()


def _get_path(value: Any, path: list[Any]) -> Any:
    current = value
    for key in path:
        if isinstance(current, dict):
            if not isinstance(key, str) or key not in current:
                return _MISSING
            current = current[key]
        elif isinstance(current, list):
            if not isinstance(key, int) or not 0 <= key < len(current):
                return _MISSING
            current = current[key]
        else:
            return _MISSING
    return current


def _set_path(value: Any, path: list[Any], new: Any) -> Any:
    if not path:
        return new
    head, rest = path[0], path[1:]
    if isinstance(value, dict):
        return {**value, head: _set_path(value[head], rest, new)}
    copy = list(value)
    copy[head] = _set_path(copy[head], rest, new)
    return copy


# ---------------------------------------------------------------- tool operators
def timeout_before_execution(
    params: dict[str, Any], _response: ToolResponse | None
) -> ToolResponse:
    return ToolResponse.timeout(str(params.get("message", "injected timeout before execution")))


def lost_ack(params: dict[str, Any], _response: ToolResponse | None) -> ToolResponse:
    return ToolResponse.timeout(str(params.get("message", "acknowledgement lost")))


def corrupt_output(params: dict[str, Any], response: ToolResponse | None) -> ToolResponse | None:
    """Replace the value at ``path`` in the delivered response; None if the path is absent."""
    assert response is not None
    path = params["path"]
    dumped = to_json_value(response)
    if _get_path(dumped, path) is _MISSING:
        return None
    return ToolResponse.model_validate(_set_path(dumped, path, params["value"]))


def wrong_retrieval(params: dict[str, Any], response: ToolResponse | None) -> ToolResponse | None:
    """F4: deliver a plausible but wrong document instead of the retrieved one (OK responses)."""
    assert response is not None
    if response.status is not EventStatus.OK:
        return None
    return ToolResponse.ok(params["data"])


# ---------------------------------------------------------------- decision operators
# Decision operators return None when they do not apply (no fault application is recorded).
def replace_decision(params: dict[str, Any], _decision: Decision) -> Decision | None:
    return Decision.model_validate(params["decision"])


def wrong_tool(params: dict[str, Any], decision: Decision) -> Decision | None:
    """F1: the agent selects a different tool (with the given args) than it intended."""
    if decision.kind != "tool_call" or decision.tool == params["tool"]:
        return None
    return Decision(
        kind="tool_call", tool=params["tool"], args=params["args"], summary=decision.summary
    )


def wrong_argument(params: dict[str, Any], decision: Decision) -> Decision | None:
    """F2: drop a required argument or replace its value in a call to ``tool``."""
    if decision.kind != "tool_call" or decision.tool != params["tool"]:
        return None
    args = dict(decision.args) if isinstance(decision.args, dict) else {}
    if params["arg"] not in args:
        return None
    if params["mode"] == "drop":
        del args[params["arg"]]
    else:
        if args[params["arg"]] == params["value"]:
            return None
        args[params["arg"]] = params["value"]
    return Decision(kind="tool_call", tool=decision.tool, args=args, summary=decision.summary)


def decoy_read(params: dict[str, Any], decision: Decision) -> Decision | None:
    """D1: a redundant read-only call instead of the intended decision (validated harmless)."""
    if decision.kind != "tool_call":
        return None
    return Decision(kind="tool_call", tool=params["tool"], args=params["args"], summary="decoy")


def _validate_tool_args(name: str, params: dict[str, Any]) -> None:
    if not isinstance(params.get("tool"), str) or not params["tool"]:
        raise FaultPlanError(f"{name} requires a 'tool' name")
    if not isinstance(params.get("args"), dict):
        raise FaultPlanError(f"{name} requires an 'args' object")
    unknown = set(params) - {"tool", "args"}
    if unknown:
        raise FaultPlanError(f"{name}: unknown params {sorted(unknown)}")


def _validate_wrong_argument(params: dict[str, Any]) -> None:
    if not isinstance(params.get("tool"), str) or not isinstance(params.get("arg"), str):
        raise FaultPlanError("WRONG_ARGUMENT requires 'tool' and 'arg' strings")
    mode = params.get("mode")
    if mode not in ("drop", "replace"):
        raise FaultPlanError("WRONG_ARGUMENT 'mode' must be 'drop' or 'replace'")
    if mode == "replace" and "value" not in params:
        raise FaultPlanError("WRONG_ARGUMENT mode 'replace' requires 'value'")


def _validate_wrong_retrieval(params: dict[str, Any]) -> None:
    if not isinstance(params.get("data"), dict) or not params["data"]:
        raise FaultPlanError("WRONG_RETRIEVAL requires a non-empty 'data' object")


def _validate_corrupt(params: dict[str, Any]) -> None:
    path = params.get("path")
    if not isinstance(path, list) or not path:
        raise FaultPlanError("CORRUPT_OUTPUT requires a non-empty 'path' list")
    if not all(isinstance(p, str | int) and not isinstance(p, bool) for p in path):
        raise FaultPlanError("CORRUPT_OUTPUT path elements must be str or int")
    if "value" not in params:
        raise FaultPlanError("CORRUPT_OUTPUT requires 'value'")


def _validate_replace(params: dict[str, Any]) -> None:
    try:
        Decision.model_validate(params.get("decision"))
    except ValueError as exc:
        raise FaultPlanError(f"REPLACE_DECISION requires a valid 'decision': {exc}") from exc


def _no_params(params: dict[str, Any]) -> None:
    unknown = set(params) - {"message"}
    if unknown:
        raise FaultPlanError(f"unknown params {sorted(unknown)}")


@dataclass(frozen=True)
class OperatorDef:
    name: str
    stage: FaultStage
    validate: Callable[[dict[str, Any]], None]
    tool_fn: Callable[[dict[str, Any], ToolResponse | None], ToolResponse | None] | None = None
    decision_fn: Callable[[dict[str, Any], Decision], Decision | None] | None = None


OPERATORS: dict[str, OperatorDef] = {
    op.name: op
    for op in (
        OperatorDef(
            "TIMEOUT_BEFORE_EXECUTION",
            FaultStage.PRE_EXECUTION,
            _no_params,
            tool_fn=timeout_before_execution,
        ),
        OperatorDef("LOST_ACK", FaultStage.POST_EXECUTION, _no_params, tool_fn=lost_ack),
        OperatorDef(
            "CORRUPT_OUTPUT", FaultStage.POST_EXECUTION, _validate_corrupt, tool_fn=corrupt_output
        ),
        OperatorDef(
            "REPLACE_DECISION", FaultStage.DECISION, _validate_replace, decision_fn=replace_decision
        ),
        OperatorDef(
            "WRONG_TOOL",
            FaultStage.DECISION,
            lambda p: _validate_tool_args("WRONG_TOOL", p),
            decision_fn=wrong_tool,
        ),
        OperatorDef(
            "WRONG_ARGUMENT",
            FaultStage.DECISION,
            _validate_wrong_argument,
            decision_fn=wrong_argument,
        ),
        OperatorDef(
            "WRONG_RETRIEVAL",
            FaultStage.POST_EXECUTION,
            _validate_wrong_retrieval,
            tool_fn=wrong_retrieval,
        ),
        OperatorDef(
            "DECOY_READ",
            FaultStage.DECISION,
            lambda p: _validate_tool_args("DECOY_READ", p),
            decision_fn=decoy_read,
        ),
    )
}
