from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from agenttrace.env.delta import json_diff
from agenttrace.env.support.models import Resolution, SupportState
from agenttrace.env.support.scenario import list_scenario_ids, load_scenario
from agenttrace.env.support.snapshot import restore, snapshot, state_hash, working_copy
from agenttrace.env.support.tools import (
    CloseTicketArgs,
    GetCustomerArgs,
    GetOrderArgs,
    IssueRefundArgs,
    SearchPolicyArgs,
    close_ticket,
    get_customer,
    get_order,
    issue_refund,
    search_policy,
    support_manifest_hash,
)


@pytest.fixture
def t1() -> SupportState:
    return restore(load_scenario("T1").initial_snapshot())


def test_get_customer_and_not_found(t1: SupportState) -> None:
    assert get_customer(t1, GetCustomerArgs(customer_id="C1")).data == {
        "customer_id": "C1",
        "name": "Synthetic Customer 1",
        "tier": "regular",
    }
    result = get_customer(t1, GetCustomerArgs(customer_id="C9"))
    assert not result.ok and result.error_code == "NOT_FOUND"


def test_get_order_money_is_json_string(t1: SupportState) -> None:
    data = get_order(t1, GetOrderArgs(order_id="O1")).data
    assert data is not None and data["total"] == "80" and data["refunded_amount"] == "0"
    assert not get_order(t1, GetOrderArgs(order_id="nope")).ok


def test_search_policy_skips_archived_docs(t1: SupportState) -> None:
    result = search_policy(t1, SearchPolicyArgs(query="damaged refund"))
    assert result.data is not None and result.data["doc_id"] == "POL-REFUND-STD"
    assert search_policy(t1, SearchPolicyArgs(query="shipping delay")).data["doc_id"] == (  # type: ignore[index]
        "POL-SHIPPING"
    )
    assert search_policy(t1, SearchPolicyArgs(query="zzz")).error_code == "NOT_FOUND"


def test_issue_refund_mutates_and_uses_state_counter(t1: SupportState) -> None:
    result = issue_refund(t1, IssueRefundArgs(order_id="O1", amount=Decimal("80")))
    assert result.ok and result.data is not None and result.data["refund_id"] == "R-0001"
    assert t1.next_refund_number == 2
    assert t1.orders["O1"].refunded_amount == Decimal("80.00")
    assert [a.action for a in t1.audit] == ["issue_refund"]


def test_issue_refund_guards(t1: SupportState) -> None:
    assert issue_refund(t1, IssueRefundArgs(order_id="O9", amount=Decimal("1"))).error_code == (
        "NOT_FOUND"
    )
    assert issue_refund(t1, IssueRefundArgs(order_id="O1", amount=Decimal("0"))).error_code == (
        "INVALID_AMOUNT"
    )
    over = issue_refund(t1, IssueRefundArgs(order_id="O1", amount=Decimal("80.01")))
    assert over.error_code == "AMOUNT_EXCEEDS_ORDER_TOTAL"
    assert t1.refunds == {}


def test_issue_refund_idempotency(t1: SupportState) -> None:
    args = IssueRefundArgs(order_id="O1", amount=Decimal("80"), idempotency_key="k1")
    first = issue_refund(t1, args)
    hash_after_first = state_hash(t1)
    second = issue_refund(t1, args)
    assert first.data is not None and second.data is not None
    assert second.data["refund_id"] == first.data["refund_id"]
    assert second.data["idempotent_replay"] is True
    assert state_hash(t1) == hash_after_first  # no second mutation
    assert len(t1.refunds) == 1 and t1.idempotency_log == {"k1": "R-0001"}


def test_refund_without_key_is_not_idempotent(t1: SupportState) -> None:
    args = IssueRefundArgs(order_id="O1", amount=Decimal("40"))
    issue_refund(t1, args)
    issue_refund(t1, args)
    assert len(t1.refunds) == 2  # tools do not dedupe; the agent must use keys


def test_close_ticket_once(t1: SupportState) -> None:
    args = CloseTicketArgs(ticket_id="TK1", resolution=Resolution.REFUNDED)
    assert close_ticket(t1, args).ok
    assert t1.tickets["TK1"].status == "closed"
    assert close_ticket(t1, args).error_code == "TICKET_ALREADY_CLOSED"


def test_args_models_reject_bad_input() -> None:
    with pytest.raises(ValidationError):
        IssueRefundArgs(order_id="O1", amount=Decimal("-1"))
    with pytest.raises(ValidationError):
        IssueRefundArgs.model_validate({"order_id": "O1"})
    with pytest.raises(ValidationError):
        CloseTicketArgs.model_validate({"ticket_id": "TK1", "resolution": "MAYBE"})
    with pytest.raises(ValidationError):
        GetOrderArgs.model_validate({"order_id": "O1", "extra": 1})


@pytest.mark.parametrize("scenario_id", list_scenario_ids())
def test_snapshot_restore_preserves_hash(scenario_id: str) -> None:
    scenario = load_scenario(scenario_id)
    state = restore(scenario.initial_snapshot())
    assert state_hash(state) == scenario.initial_state_hash()
    assert snapshot(restore(snapshot(state))) == snapshot(state)


def test_restore_returns_independent_objects(t1: SupportState) -> None:
    other = restore(snapshot(t1))
    other.orders["O1"].refunded_amount = Decimal("1.00")
    assert t1.orders["O1"].refunded_amount == Decimal("0.00")


def test_working_copy_is_deep(t1: SupportState) -> None:
    copy = working_copy(t1)
    issue_refund(copy, IssueRefundArgs(order_id="O1", amount=Decimal("10")))
    assert t1.refunds == {} and t1.next_refund_number == 1


def test_scenario_model_rejects_inconsistent_state() -> None:
    raw = load_scenario("T1").model_dump(mode="json")
    raw["initial_state"]["orders"]["O1"]["total"] = "79.00"
    with pytest.raises(ValidationError, match="total"):
        type(load_scenario("T1")).model_validate(raw)


def test_manifest_hash_is_stable() -> None:
    assert support_manifest_hash() == support_manifest_hash()


def test_json_diff_paths() -> None:
    before = {"a": {"x": 1}, "l": [1], "r": "gone"}
    after = {"a": {"x": 2}, "l": [1, 2], "n/k": True}
    ops = [(op.op, op.path) for op in json_diff(before, after)]
    assert ops == [("replace", "/a/x"), ("add", "/l/1"), ("add", "/n~1k"), ("remove", "/r")]
    assert json_diff(before, before) == []


# P3 (basic Week 1 version): snapshot -> restore -> hash round-trip on generated variants.
@settings(max_examples=50)
@given(
    scenario_id=st.sampled_from(list_scenario_ids()),
    refunded=st.decimals(min_value=0, max_value=40, places=2),
    counter=st.integers(min_value=1, max_value=9999),
)
def test_p3_snapshot_roundtrip(scenario_id: str, refunded: Decimal, counter: int) -> None:
    state = restore(load_scenario(scenario_id).initial_snapshot())
    order = next(iter(state.orders.values()))
    order.refunded_amount = refunded
    state.next_refund_number = counter
    again = restore(snapshot(state))
    assert state_hash(again) == state_hash(state)
    assert again == state
