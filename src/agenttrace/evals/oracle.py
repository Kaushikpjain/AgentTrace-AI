"""Deterministic task-success oracle for the support environment (no LLM judge)."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from agenttrace.env.support.models import SupportState
from agenttrace.env.support.scenario import ExpectedOutcome
from agenttrace.trace.canonical import decimal_to_str
from agenttrace.trace.schema import OracleRef, Outcome, OutcomeRecord, ViolatedClause

ORACLE_REF = OracleRef(id="support-oracle", version="1.0")

CLAUSE_REFUND_SET = "REFUND_SET"
CLAUSE_NO_DUPLICATE = "NO_DUPLICATE_REFUND"
CLAUSE_NO_OVER_REFUND = "NO_OVER_REFUND"
CLAUSE_TICKET_STATE = "TICKET_STATE"


def _fmt(pairs: Counter[tuple[str, Decimal]]) -> str:
    items = sorted((o, decimal_to_str(a), n) for (o, a), n in pairs.items())
    return ", ".join(f"{o}:{a}x{n}" for o, a, n in items) or "none"


def evaluate(expected: ExpectedOutcome, state: SupportState) -> OutcomeRecord:
    """Evaluate all clauses; the outcome is PASS iff no clause is violated."""
    violated: list[ViolatedClause] = []

    actual = Counter((r.order_id, r.amount) for r in state.refunds.values())
    wanted = Counter((r.order_id, r.amount) for r in expected.refunds)
    if actual != wanted:
        violated.append(
            ViolatedClause(
                clause_id=CLAUSE_REFUND_SET,
                message=f"refunds expected [{_fmt(wanted)}], found [{_fmt(actual)}]",
            )
        )

    duplicates = {pair: n for pair, n in actual.items() if n > 1}
    if duplicates:
        violated.append(
            ViolatedClause(
                clause_id=CLAUSE_NO_DUPLICATE,
                message=f"duplicate refunds: [{_fmt(Counter(duplicates))}]",
            )
        )

    per_order: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for refund in state.refunds.values():
        per_order[refund.order_id] += refund.amount
    over = sorted(o for o, total in per_order.items() if total > state.orders[o].total)
    if over:
        violated.append(
            ViolatedClause(
                clause_id=CLAUSE_NO_OVER_REFUND,
                message=f"refunds exceed order total for: {', '.join(over)}",
            )
        )

    ticket = state.tickets.get(expected.ticket.ticket_id)
    want = expected.ticket
    if ticket is None or (ticket.status, ticket.resolution) != (want.status, want.resolution):
        found = "missing" if ticket is None else f"{ticket.status}/{ticket.resolution}"
        violated.append(
            ViolatedClause(
                clause_id=CLAUSE_TICKET_STATE,
                message=f"ticket {want.ticket_id} expected {want.status}/{want.resolution}, "
                f"found {found}",
            )
        )

    return OutcomeRecord(
        outcome=Outcome.FAIL if violated else Outcome.PASS,
        violated_clauses=tuple(violated),
    )
