"""Environment-agnostic tool contract used by the runtime gateway.

A tool is a deterministic function ``fn(state, args) -> ToolResult`` that may mutate the
*working copy* it receives. It never touches the live state, the network, the filesystem,
clocks or randomness. Committing the working copy is the gateway's job (REPLAY_SPEC S4).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from pydantic import BaseModel

from agenttrace.trace.canonical import JsonValue, to_json_value
from agenttrace.trace.fingerprint import fingerprint, fingerprint_text


@dataclass(frozen=True)
class ToolResult:
    """Raw result of a tool execution (before any post-execution fault)."""

    ok: bool
    data: dict[str, JsonValue] | None = None
    error_code: str | None = None
    message: str | None = None

    @staticmethod
    def success(data: Mapping[str, Any]) -> ToolResult:
        converted = to_json_value(dict(data))
        assert isinstance(converted, dict)
        return ToolResult(ok=True, data=converted)

    @staticmethod
    def failure(code: str, message: str) -> ToolResult:
        return ToolResult(ok=False, error_code=code, message=message)


@dataclass(frozen=True)
class ToolSpec[S: BaseModel]:
    name: str
    args_model: type[BaseModel]
    mutating: bool
    fn: Callable[[S, Any], ToolResult]
    description: str = ""


def manifest_hash(tools: Sequence[ToolSpec[Any]], module: ModuleType) -> str:
    """Hash of tool names, mutating flags, argument schemas and implementation source (ADR-012)."""
    return fingerprint(
        {
            "tools": [
                {
                    "name": tool.name,
                    "mutating": tool.mutating,
                    "args_schema": to_json_value(tool.args_model.model_json_schema()),
                }
                for tool in tools
            ],
            "source": fingerprint_text(inspect.getsource(module)),
        }
    )
