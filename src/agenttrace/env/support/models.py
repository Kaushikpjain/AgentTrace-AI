"""State model of the synthetic customer-support / order-management sandbox.

All data is synthetic. Money is Decimal quantized to 2 places (ADR-013). Identifiers
for new records come from counters inside the state (ADR-008), so snapshots capture them.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

_CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError("money must be a finite, non-negative Decimal")
    return value.quantize(_CENT, rounding=ROUND_HALF_EVEN)


Money = Annotated[Decimal, AfterValidator(_money)]
Tier = Literal["regular", "gold"]
OrderStatus = Literal["delivered", "shipped"]
Issue = Literal["damaged", "not_received"]


class Resolution(StrEnum):
    REFUNDED = "REFUNDED"
    ESCALATED = "ESCALATED"
    DENIED = "DENIED"
    PENDING_DELIVERY = "PENDING_DELIVERY"
    ALREADY_REFUNDED = "ALREADY_REFUNDED"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Customer(_Model):
    customer_id: str
    name: str
    tier: Tier


class OrderItem(_Model):
    sku: str
    description: str
    unit_price: Money
    quantity: int = Field(ge=1)

    @property
    def line_total(self) -> Decimal:
        return _money(self.unit_price * self.quantity)


class Order(_Model):
    order_id: str
    customer_id: str
    status: OrderStatus
    final_sale: bool = False
    items: list[OrderItem] = Field(min_length=1)
    total: Money
    refunded_amount: Money = Decimal("0.00")

    @model_validator(mode="after")
    def _total_matches_items(self) -> Self:
        if _money(sum((item.line_total for item in self.items), Decimal(0))) != self.total:
            raise ValueError(f"order {self.order_id}: total does not equal the sum of its items")
        return self


class Refund(_Model):
    refund_id: str
    order_id: str
    amount: Money
    idempotency_key: str | None = None


class Ticket(_Model):
    ticket_id: str
    customer_id: str
    order_id: str
    issue: Issue
    sku: str | None = None
    status: Literal["open", "closed"] = "open"
    resolution: Resolution | None = None
    note: str | None = None


class PolicyRules(_Model):
    refund_limit: dict[Tier, Money]
    refundable_statuses: list[OrderStatus]
    final_sale_refundable: bool


class PolicyDoc(_Model):
    doc_id: str
    title: str
    keywords: list[str]
    archived: bool = False
    rules: PolicyRules


class AuditEntry(_Model):
    action: str
    target: str
    detail: dict[str, str]


class SupportState(_Model):
    customers: dict[str, Customer] = Field(default_factory=dict)
    orders: dict[str, Order] = Field(default_factory=dict)
    refunds: dict[str, Refund] = Field(default_factory=dict)
    tickets: dict[str, Ticket] = Field(default_factory=dict)
    policy_docs: dict[str, PolicyDoc] = Field(default_factory=dict)
    idempotency_log: dict[str, str] = Field(default_factory=dict)
    audit: list[AuditEntry] = Field(default_factory=list)
    next_refund_number: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        for key, model, attr in (
            *((k, v, "customer_id") for k, v in self.customers.items()),
            *((k, v, "order_id") for k, v in self.orders.items()),
            *((k, v, "refund_id") for k, v in self.refunds.items()),
            *((k, v, "ticket_id") for k, v in self.tickets.items()),
            *((k, v, "doc_id") for k, v in self.policy_docs.items()),
        ):
            if getattr(model, attr) != key:
                raise ValueError(f"key {key!r} does not match {attr}")
        for order in self.orders.values():
            if order.customer_id not in self.customers:
                raise ValueError(f"order {order.order_id} references unknown customer")
        for refund in self.refunds.values():
            if refund.order_id not in self.orders:
                raise ValueError(f"refund {refund.refund_id} references unknown order")
        for ticket in self.tickets.values():
            if ticket.order_id not in self.orders or ticket.customer_id not in self.customers:
                raise ValueError(f"ticket {ticket.ticket_id} references unknown records")
        for refund_id in self.idempotency_log.values():
            if refund_id not in self.refunds:
                raise ValueError(f"idempotency log references unknown refund {refund_id}")
        return self
