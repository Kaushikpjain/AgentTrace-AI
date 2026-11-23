"""The five sandboxed support tools. Pure functions over an in-memory working copy.

Tools validate business preconditions and return structured errors. They do NOT enforce
refund limits or cumulative refund caps: that is the agent's job and is checked by the
oracle (a deliberate sandbox property, so duplicate-refund failures are observable).
"""

from __future__ import annotations

import re
import sys
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agenttrace.env.base import ToolResult, ToolSpec, manifest_hash
from agenttrace.env.support.models import AuditEntry, Money, Refund, Resolution, SupportState
from agenttrace.trace.canonical import decimal_to_str

_WORD = re.compile(r"[a-z0-9]+")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GetCustomerArgs(_Args):
    customer_id: str = Field(min_length=1, max_length=64)


class GetOrderArgs(_Args):
    order_id: str = Field(min_length=1, max_length=64)


class SearchPolicyArgs(_Args):
    query: str = Field(min_length=1, max_length=200)


class IssueRefundArgs(_Args):
    order_id: str = Field(min_length=1, max_length=64)
    amount: Money
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class CloseTicketArgs(_Args):
    ticket_id: str = Field(min_length=1, max_length=64)
    resolution: Resolution
    note: str | None = Field(default=None, max_length=500)


def get_customer(state: SupportState, args: GetCustomerArgs) -> ToolResult:
    customer = state.customers.get(args.customer_id)
    if customer is None:
        return ToolResult.failure("NOT_FOUND", f"customer {args.customer_id} not found")
    return ToolResult.success(customer.model_dump())


def get_order(state: SupportState, args: GetOrderArgs) -> ToolResult:
    order = state.orders.get(args.order_id)
    if order is None:
        return ToolResult.failure("NOT_FOUND", f"order {args.order_id} not found")
    return ToolResult.success(order.model_dump())


def search_policy(state: SupportState, args: SearchPolicyArgs) -> ToolResult:
    tokens = set(_WORD.findall(args.query.lower()))
    best: tuple[int, str] | None = None
    for doc in sorted(state.policy_docs.values(), key=lambda d: d.doc_id):
        if doc.archived:
            continue
        score = len(tokens & {k.lower() for k in doc.keywords})
        if score > 0 and (best is None or score > best[0]):
            best = (score, doc.doc_id)
    if best is None:
        return ToolResult.failure("NOT_FOUND", "no policy document matches the query")
    return ToolResult.success(state.policy_docs[best[1]].model_dump())


def issue_refund(state: SupportState, args: IssueRefundArgs) -> ToolResult:
    if args.idempotency_key is not None and args.idempotency_key in state.idempotency_log:
        existing = state.refunds[state.idempotency_log[args.idempotency_key]]
        return ToolResult.success({**existing.model_dump(), "idempotent_replay": True})
    order = state.orders.get(args.order_id)
    if order is None:
        return ToolResult.failure("NOT_FOUND", f"order {args.order_id} not found")
    if args.amount <= Decimal(0):
        return ToolResult.failure("INVALID_AMOUNT", "refund amount must be positive")
    if args.amount > order.total:
        return ToolResult.failure("AMOUNT_EXCEEDS_ORDER_TOTAL", "refund exceeds the order total")
    refund_id = f"R-{state.next_refund_number:04d}"
    state.next_refund_number += 1
    refund = Refund(
        refund_id=refund_id,
        order_id=order.order_id,
        amount=args.amount,
        idempotency_key=args.idempotency_key,
    )
    state.refunds[refund_id] = refund
    order.refunded_amount = order.refunded_amount + args.amount
    if args.idempotency_key is not None:
        state.idempotency_log[args.idempotency_key] = refund_id
    state.audit.append(
        AuditEntry(
            action="issue_refund",
            target=refund_id,
            detail={"order_id": order.order_id, "amount": decimal_to_str(args.amount)},
        )
    )
    return ToolResult.success({**refund.model_dump(), "idempotent_replay": False})


def close_ticket(state: SupportState, args: CloseTicketArgs) -> ToolResult:
    ticket = state.tickets.get(args.ticket_id)
    if ticket is None:
        return ToolResult.failure("NOT_FOUND", f"ticket {args.ticket_id} not found")
    if ticket.status == "closed":
        return ToolResult.failure("TICKET_ALREADY_CLOSED", f"ticket {args.ticket_id} is closed")
    ticket.status = "closed"
    ticket.resolution = args.resolution
    ticket.note = args.note
    state.audit.append(
        AuditEntry(
            action="close_ticket",
            target=ticket.ticket_id,
            detail={"resolution": args.resolution.value},
        )
    )
    return ToolResult.success(ticket.model_dump())


SUPPORT_TOOLS: tuple[ToolSpec[Any], ...] = (
    ToolSpec("get_customer", GetCustomerArgs, False, get_customer, "Look up a customer"),
    ToolSpec("get_order", GetOrderArgs, False, get_order, "Look up an order"),
    ToolSpec("search_policy", SearchPolicyArgs, False, search_policy, "Find a policy document"),
    ToolSpec("issue_refund", IssueRefundArgs, True, issue_refund, "Issue a refund (mutating)"),
    ToolSpec("close_ticket", CloseTicketArgs, True, close_ticket, "Close a ticket (mutating)"),
)

SUPPORT_TOOLS_BY_NAME: dict[str, ToolSpec[Any]] = {tool.name: tool for tool in SUPPORT_TOOLS}


def support_manifest_hash() -> str:
    return manifest_hash(SUPPORT_TOOLS, sys.modules[__name__])
