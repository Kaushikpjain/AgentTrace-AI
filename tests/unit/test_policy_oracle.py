from __future__ import annotations

from decimal import Decimal

import pytest

from agenttrace.env.support.models import Refund, Resolution
from agenttrace.env.support.scenario import load_scenario
from agenttrace.env.support.snapshot import restore
from agenttrace.evals.oracle import (
    CLAUSE_NO_DUPLICATE,
    CLAUSE_NO_OVER_REFUND,
    CLAUSE_REFUND_SET,
    CLAUSE_TICKET_STATE,
    evaluate,
)
from agenttrace.policies.reference import GoldSupportReference
from agenttrace.policies.support_scripted import ScriptedSupportPolicy
from agenttrace.runner import record_scenario
from agenttrace.runtime.types import Decision
from agenttrace.trace.schema import Boundary, EventStatus, Outcome, RunStatus
from tests import plans


def _tool_sequence(record) -> list[str]:  # type: ignore[no-untyped-def]
    return [e.name for e in record.events if e.boundary is Boundary.TOOL]


@pytest.mark.parametrize(
    ("scenario_id", "expected_tools"),
    [
        ("T1", ["get_customer", "get_order", "search_policy", "issue_refund", "close_ticket"]),
        ("T2", ["get_customer", "get_order", "search_policy", "close_ticket"]),
        ("T5", ["get_customer", "get_order", "search_policy", "close_ticket"]),
    ],
)
def test_scripted_flows(scenario_id: str, expected_tools: list[str]) -> None:
    record = record_scenario(load_scenario(scenario_id))
    assert _tool_sequence(record) == expected_tools


def test_v2_uses_idempotency_key_v1_does_not() -> None:
    v1 = record_scenario(load_scenario("T1"), policy_version="v1")
    v2 = record_scenario(load_scenario("T1"), policy_version="v2")
    refund_v1 = next(e for e in v1.events if e.name == "issue_refund")
    refund_v2 = next(e for e in v2.events if e.name == "issue_refund")
    assert "idempotency_key" not in refund_v1.request["args"]  # type: ignore[index]
    assert refund_v2.request["args"]["idempotency_key"] == "refund:TK1"  # type: ignore[index]


def test_lost_ack_v1_duplicates_refund_and_fails_oracle() -> None:
    record = record_scenario(load_scenario("T1"), policy_version="v1", fault_plan=plans.lost_ack())
    assert _tool_sequence(record).count("issue_refund") == 2
    clauses = {c.clause_id for c in record.footer.outcome.violated_clauses}
    assert record.footer.outcome.outcome is Outcome.FAIL
    assert {CLAUSE_REFUND_SET, CLAUSE_NO_DUPLICATE, CLAUSE_NO_OVER_REFUND} <= clauses


def test_lost_ack_v2_idempotent_retry_passes() -> None:
    record = record_scenario(load_scenario("T1"), policy_version="v2", fault_plan=plans.lost_ack())
    refunds = [e for e in record.events if e.name == "issue_refund"]
    assert [e.status for e in refunds] == [EventStatus.TIMEOUT, EventStatus.OK]
    assert refunds[0].state.committed and not refunds[1].state.committed  # type: ignore[union-attr]
    assert record.footer.outcome.outcome is Outcome.PASS


def test_pre_execution_timeout_v1_retry_passes() -> None:
    record = record_scenario(
        load_scenario("T1"), policy_version="v1", fault_plan=plans.pre_execution_timeout()
    )
    refunds = [e for e in record.events if e.name == "issue_refund"]
    assert not refunds[0].state.committed and refunds[1].state.committed  # type: ignore[union-attr]
    assert record.footer.outcome.outcome is Outcome.PASS


def test_decision_fault_recorded_raw_vs_delivered() -> None:
    # Replace the 4th decision (the refund) with a wrong-tool decision (F1-like).
    plan = plans.replace_decision(
        4,
        Decision.call(
            "close_ticket", ticket_id="TK1", resolution=Resolution.DENIED.value, note="x"
        ),
    )
    record = record_scenario(load_scenario("T1"), fault_plan=plan)
    decisions = [
        (e, entry)
        for e, entry in zip(
            [e for e in record.events if e.boundary in (Boundary.DECISION, Boundary.TOOL)],
            record.ledger,
            strict=True,
        )
        if e.boundary is Boundary.DECISION
    ]
    event, entry = decisions[3]
    assert event.response["tool"] == "close_ticket"  # type: ignore[index]
    assert entry.raw_output["tool"] == "issue_refund"  # type: ignore[index]
    assert entry.fault_applications and record.footer.outcome.outcome is Outcome.FAIL


def test_max_steps_guard() -> None:
    record = record_scenario(load_scenario("T1"), max_steps=2)
    assert record.footer.status is RunStatus.MAX_STEPS
    assert record.footer.totals.steps == 2
    assert record.footer.outcome.outcome is Outcome.FAIL  # ticket never closed


def test_reference_policy_matches_gold_v2() -> None:
    ref = GoldSupportReference()
    task = load_scenario("T1").task
    assert ref.reference_decision(task, ()) == ScriptedSupportPolicy("v2").decide(task, ())
    assert ref.reference_id == "support-scripted:v2:gold"


def test_policy_identity() -> None:
    v1, v2 = ScriptedSupportPolicy("v1"), ScriptedSupportPolicy("v2")
    assert v1.deterministic and v1.source_hash == v2.source_hash
    assert v1.policy_version != v2.policy_version
    with pytest.raises(ValueError):
        ScriptedSupportPolicy("v3")  # type: ignore[arg-type]


# ------------------------------------------------------------------ oracle clauses
def _final_state(scenario_id: str):  # type: ignore[no-untyped-def]
    scenario = load_scenario(scenario_id)
    return scenario, restore(scenario.initial_snapshot())


def test_oracle_initial_state_fails_ticket_clause() -> None:
    scenario, state = _final_state("T2")
    result = evaluate(scenario.expected, state)
    assert [c.clause_id for c in result.violated_clauses] == [CLAUSE_TICKET_STATE]


def test_oracle_wrong_amount_and_over_refund() -> None:
    scenario, state = _final_state("T1")
    state.refunds["R-0001"] = Refund(refund_id="R-0001", order_id="O1", amount=Decimal("90"))
    ticket = state.tickets["TK1"]
    ticket.status, ticket.resolution = "closed", Resolution.REFUNDED
    ids = [c.clause_id for c in evaluate(scenario.expected, state).violated_clauses]
    assert ids == [CLAUSE_REFUND_SET, CLAUSE_NO_OVER_REFUND]


def test_oracle_pass() -> None:
    scenario, state = _final_state("T2")
    ticket = state.tickets["TK2"]
    ticket.status, ticket.resolution = "closed", Resolution.ESCALATED
    assert evaluate(scenario.expected, state).outcome is Outcome.PASS
