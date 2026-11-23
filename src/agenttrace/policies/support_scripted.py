"""Deterministic scripted support agent (ADR-004).

A pure function of (task, history). Versions:
- ``v1``: issues refunds WITHOUT an idempotency key and retries once after a timeout.
  Under a lost acknowledgement this produces a duplicate refund (a realistic agent bug).
- ``v2``: identical, but uses a deterministic idempotency key, so the retry is safe.

The flow: get_customer -> get_order -> search_policy -> decide -> (issue_refund) ->
close_ticket -> final. Any unexpected tool error escalates the ticket.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal

from agenttrace.env.support.models import Resolution
from agenttrace.env.support.scenario import TaskSpec
from agenttrace.runtime.types import Decision, Observation
from agenttrace.trace.fingerprint import fingerprint_text
from agenttrace.trace.schema import EventStatus

PolicyVersion = Literal["v1", "v2"]
MAX_REFUND_ATTEMPTS = 2


def _last(history: Sequence[Observation], tool: str) -> Observation | None:
    for obs in reversed(history):
        if obs.tool == tool:
            return obs
    return None


def _data(obs: Observation) -> dict[str, Any]:
    data = obs.response.data
    return data if isinstance(data, dict) else {}


def _close(task: TaskSpec, resolution: Resolution, note: str) -> Decision:
    return Decision.call(
        "close_ticket",
        summary=f"close ticket as {resolution.value}",
        ticket_id=task.ticket_id,
        resolution=resolution.value,
        note=note,
    )


class ScriptedSupportPolicy:
    policy_id = "support-scripted"

    def __init__(self, version: PolicyVersion = "v1") -> None:
        if version not in ("v1", "v2"):
            raise ValueError(f"unknown policy version {version!r}")
        self._version: PolicyVersion = version

    @property
    def policy_version(self) -> str:
        return self._version

    @property
    def source_hash(self) -> str:
        return fingerprint_text(inspect.getsource(sys.modules[__name__]))

    @property
    def deterministic(self) -> bool:
        return True

    def _refund_call(self, task: TaskSpec, amount: Decimal) -> Decision:
        args: dict[str, Any] = {"order_id": task.order_id, "amount": amount}
        if self._version == "v2":
            args["idempotency_key"] = f"refund:{task.ticket_id}"
        return Decision.call("issue_refund", summary="issue refund", **args)

    def decide(self, task: TaskSpec, history: Sequence[Observation]) -> Decision:
        closed = _last(history, "close_ticket")
        if closed is not None:
            return Decision.final(summary=f"ticket closed ({closed.response.status.value})")

        customer = _last(history, "get_customer")
        if customer is None:
            return Decision.call("get_customer", customer_id=task.customer_id)
        if customer.response.status is not EventStatus.OK:
            return _close(task, Resolution.ESCALATED, "customer lookup failed")

        order = _last(history, "get_order")
        if order is None:
            return Decision.call("get_order", order_id=task.order_id)
        if order.response.status is not EventStatus.OK:
            return _close(task, Resolution.ESCALATED, "order lookup failed")

        policy = _last(history, "search_policy")
        if policy is None:
            query = f"{task.issue.replace('_', ' ')} refund"
            return Decision.call("search_policy", query=query)
        if policy.response.status is not EventStatus.OK:
            return _close(task, Resolution.ESCALATED, "no applicable policy found")

        order_data, rules = _data(order), _data(policy).get("rules", {})
        tier = _data(customer).get("tier", "regular")

        refund_attempts = [obs for obs in history if obs.tool == "issue_refund"]
        if refund_attempts:
            last = refund_attempts[-1].response
            if last.status is EventStatus.OK:
                return _close(task, Resolution.REFUNDED, "refund issued")
            if last.status is EventStatus.TIMEOUT and len(refund_attempts) < MAX_REFUND_ATTEMPTS:
                return self._refund_call(task, Decimal(str(refund_attempts[-1].args["amount"])))
            return _close(task, Resolution.ESCALATED, "refund could not be completed")

        if order_data.get("status") not in rules.get("refundable_statuses", []):
            return _close(task, Resolution.PENDING_DELIVERY, "order not yet delivered")

        amount: Decimal
        if task.sku is not None:
            lines = [i for i in order_data.get("items", []) if i.get("sku") == task.sku]
            if not lines:
                return _close(task, Resolution.ESCALATED, f"item {task.sku} not in order")
            amount = Decimal(str(lines[0]["unit_price"])) * int(lines[0]["quantity"])
        else:
            amount = Decimal(str(order_data.get("total", "0")))

        if Decimal(str(order_data.get("refunded_amount", "0"))) >= amount:
            return _close(task, Resolution.ALREADY_REFUNDED, "refund already issued")
        if order_data.get("final_sale") and not rules.get("final_sale_refundable", False):
            return _close(task, Resolution.DENIED, "final-sale items are not refundable")
        limit = Decimal(str(rules.get("refund_limit", {}).get(tier, "0")))
        if amount > limit:
            return _close(task, Resolution.ESCALATED, "amount exceeds the agent refund limit")
        return self._refund_call(task, amount)
