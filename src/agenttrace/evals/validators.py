"""Deterministic validators over the OBSERVABLE trace of the support environment (W3.5).

Each flag is a supporting observation attached to an event seq. Validators read only what an
operator of the sandbox could observe: requests, delivered responses and state transitions.
They never read the ledger, fault plans or labels.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from agenttrace.trace.schema import Boundary, Event, EventStatus, Trace

FLAG_ERROR = "TOOL_ERROR"
FLAG_TIMEOUT = "TOOL_TIMEOUT"
FLAG_INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
FLAG_UNKNOWN_TOOL = "UNKNOWN_TOOL"
FLAG_OUTPUT_INCONSISTENT = "OUTPUT_INCONSISTENT"  # e.g. order total != sum of items
FLAG_ARCHIVED_POLICY = "RETRIEVED_ARCHIVED_POLICY"
FLAG_REFUND_OVER_LIMIT = "REFUND_EXCEEDS_OBSERVED_LIMIT"
FLAG_REPEATED_MUTATION = "REPEATED_MUTATING_CALL"
FLAG_TIMEOUT_WITH_COMMIT = "TIMEOUT_BUT_STATE_COMMITTED"

MUTATING_TOOLS = frozenset({"issue_refund", "close_ticket"})


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _data(event: Event) -> dict[str, Any]:
    response = event.response if isinstance(event.response, dict) else {}
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def _args(event: Event) -> dict[str, Any]:
    request = event.request if isinstance(event.request, dict) else {}
    args = request.get("args")
    return args if isinstance(args, dict) else {}


def support_flags(trace: Trace) -> Mapping[int, tuple[str, ...]]:
    flags: dict[int, list[str]] = {}

    def add(seq: int, flag: str) -> None:
        flags.setdefault(seq, []).append(flag)

    tier: str | None = None
    rules: dict[str, Any] = {}
    for event in trace.events:
        if event.boundary is not Boundary.TOOL:
            continue
        response = event.response if isinstance(event.response, dict) else {}
        error = response.get("error") if isinstance(response.get("error"), dict) else None
        if event.status is EventStatus.TIMEOUT:
            add(event.seq, FLAG_TIMEOUT)
            if event.state is not None and event.state.committed:
                add(event.seq, FLAG_TIMEOUT_WITH_COMMIT)
        elif event.status is EventStatus.ERROR:
            code = error.get("code") if error else None
            if code == "INVALID_ARGUMENTS":
                add(event.seq, FLAG_INVALID_ARGUMENTS)
            elif code == "UNKNOWN_TOOL":
                add(event.seq, FLAG_UNKNOWN_TOOL)
            else:
                add(event.seq, FLAG_ERROR)
        data = _data(event)
        if event.name == "get_customer" and isinstance(data.get("tier"), str):
            tier = data["tier"]
        if event.name == "get_order" and data:
            items = data.get("items")
            total = _dec(data.get("total"))
            if isinstance(items, list) and total is not None:
                computed = sum(
                    (
                        (_dec(i.get("unit_price")) or Decimal(0)) * int(i.get("quantity", 0))
                        for i in items
                        if isinstance(i, dict)
                    ),
                    Decimal(0),
                )
                if computed != total:
                    add(event.seq, FLAG_OUTPUT_INCONSISTENT)
        if event.name == "search_policy" and data:
            if data.get("archived") is True:
                add(event.seq, FLAG_ARCHIVED_POLICY)
            if isinstance(data.get("rules"), dict):
                rules = data["rules"]
        if event.name == "issue_refund":
            amount = _dec(_args(event).get("amount"))
            limits = rules.get("refund_limit") if isinstance(rules, dict) else None
            limit = _dec(limits.get(tier)) if isinstance(limits, dict) and tier else None
            if amount is not None and limit is not None and amount > limit:
                add(event.seq, FLAG_REFUND_OVER_LIMIT)
        if event.name in MUTATING_TOOLS and (event.attempt or 1) > 1:
            add(event.seq, FLAG_REPEATED_MUTATION)
    return {seq: tuple(values) for seq, values in flags.items()}
