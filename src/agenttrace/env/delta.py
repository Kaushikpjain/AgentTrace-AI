"""Structural JSON diff producing JSON-pointer-style delta operations.

Used to record the state transition of a committed tool call. Environment-agnostic:
operates on JSON-pure values (see trace.canonical.to_json_value).
"""

from __future__ import annotations

from agenttrace.trace.canonical import JsonValue
from agenttrace.trace.schema import DeltaOp


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def json_diff(before: JsonValue, after: JsonValue, path: str = "") -> list[DeltaOp]:
    """Return the operations that transform ``before`` into ``after`` (deterministic order)."""
    if isinstance(before, dict) and isinstance(after, dict):
        ops: list[DeltaOp] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{_escape(key)}"
            if key not in after:
                ops.append(DeltaOp(op="remove", path=child, old=before[key]))
            elif key not in before:
                ops.append(DeltaOp(op="add", path=child, new=after[key]))
            else:
                ops.extend(json_diff(before[key], after[key], child))
        return ops
    if isinstance(before, list) and isinstance(after, list):
        ops = []
        for index in range(max(len(before), len(after))):
            child = f"{path}/{index}"
            if index >= len(after):
                ops.append(DeltaOp(op="remove", path=child, old=before[index]))
            elif index >= len(before):
                ops.append(DeltaOp(op="add", path=child, new=after[index]))
            else:
                ops.extend(json_diff(before[index], after[index], child))
        return ops
    if before == after and type(before) is type(after):
        return []
    return [DeltaOp(op="replace", path=path or "/", old=before, new=after)]
