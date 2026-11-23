"""Tool lifecycle S1-S7 and decision lifecycle D1-D4 (REPLAY_SPEC sections 3-4)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from agenttrace.env.base import ToolResult, ToolSpec
from agenttrace.env.support.models import SupportState
from agenttrace.env.support.scenario import load_scenario
from agenttrace.env.support.snapshot import restore, state_hash
from agenttrace.env.support.tools import SUPPORT_TOOLS_BY_NAME
from agenttrace.runtime.faults import FaultHook, NoFaults
from agenttrace.runtime.gateway import BoundaryGateway, ReadOnlyToolMutatedState
from agenttrace.runtime.types import Decision
from agenttrace.trace.schema import EventStatus, FaultStage
from tests.hooks import LostAck, PreExecutionTimeout


def _gateway(
    hook: FaultHook | None = None, tools: dict[str, ToolSpec[Any]] | None = None
) -> BoundaryGateway[SupportState]:
    return BoundaryGateway(
        run_id="run-gw",
        state=restore(load_scenario("T1").initial_snapshot()),
        tools=tools if tools is not None else dict(SUPPORT_TOOLS_BY_NAME),
        fault_hook=hook if hook is not None else NoFaults(),
    )


def _call(gw: BoundaryGateway[SupportState], tool: str, **args: Any) -> Any:
    span = gw.open_step(0)
    return gw.call_tool(Decision.call(tool, **args), step_index=0, parent_span_id=span)


REFUND = {"order_id": "O1", "amount": "80"}


def test_unknown_tool_is_not_executed() -> None:
    gw = _gateway()
    response = _call(gw, "delete_database")
    assert response.status is EventStatus.ERROR and response.error.code == "UNKNOWN_TOOL"
    event, entry = gw.events[-1], gw.ledger[-1]
    assert entry.executed is False and entry.raw_output is None
    assert event.state is not None and not event.state.committed


def test_invalid_arguments_are_not_executed() -> None:
    gw = _gateway()
    before = gw.state_hash()
    response = _call(gw, "issue_refund", order_id="O1")  # missing amount
    assert response.error.code == "INVALID_ARGUMENTS"
    assert "amount: missing" in response.error.message
    assert gw.ledger[-1].executed is False and gw.state_hash() == before


def test_read_only_call_never_commits() -> None:
    gw = _gateway()
    before = gw.state_hash()
    _call(gw, "get_order", order_id="O1")
    event, entry = gw.events[-1], gw.ledger[-1]
    assert entry.executed is True and entry.raw_output_fp == event.response_fp
    assert event.state is not None and not event.state.committed
    assert event.state.before_hash == event.state.after_hash == before == gw.state_hash()


def test_mutating_call_commits_with_delta() -> None:
    gw = _gateway()
    before = gw.state_hash()
    response = _call(gw, "issue_refund", **REFUND)
    assert response.status is EventStatus.OK
    state = gw.events[-1].state
    assert state is not None and state.committed and state.before_hash == before
    assert state.after_hash == gw.state_hash() != before
    paths = {op.path for op in state.delta}
    assert "/refunds/R-0001" in paths and "/next_refund_number" in paths


def test_failed_mutating_call_rolls_back() -> None:
    gw = _gateway()
    before = gw.state_hash()
    response = _call(gw, "issue_refund", order_id="O1", amount="999")
    assert response.error.code == "AMOUNT_EXCEEDS_ORDER_TOTAL"
    assert gw.ledger[-1].executed is True
    assert not gw.events[-1].state.committed and gw.state_hash() == before  # type: ignore[union-attr]


class _NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _crashing_tool(state: SupportState, args: _NoArgs) -> ToolResult:
    state.next_refund_number = 77  # mutate the working copy, then crash
    raise RuntimeError("boom")


def _sneaky_reader(state: SupportState, args: _NoArgs) -> ToolResult:
    state.next_refund_number = 99
    return ToolResult.success({})


def test_tool_exception_is_structured_and_not_committed() -> None:
    gw = _gateway(tools={"crash": ToolSpec("crash", _NoArgs, True, _crashing_tool)})
    before = gw.state_hash()
    response = _call(gw, "crash")
    assert response.error.code == "TOOL_EXCEPTION" and response.error.message == "RuntimeError"
    assert gw.state_hash() == before and gw.state.next_refund_number == 1


def test_read_only_tool_mutation_is_a_programming_error() -> None:
    gw = _gateway(tools={"sneaky": ToolSpec("sneaky", _NoArgs, False, _sneaky_reader)})
    with pytest.raises(ReadOnlyToolMutatedState):
        _call(gw, "sneaky")


def test_attempt_numbering_and_logical_keys() -> None:
    gw = _gateway()
    _call(gw, "get_order", order_id="O1")
    _call(gw, "get_order", order_id="O1")
    _call(gw, "get_customer", customer_id="C1")
    tools = [e for e in gw.events if e.boundary.value == "TOOL"]
    assert [e.attempt for e in tools] == [1, 2, 1]
    assert [e.logical_key for e in tools] == [
        "0:TOOL:get_order#1",
        "0:TOOL:get_order#2",
        "0:TOOL:get_customer#1",
    ]
    assert [e.seq for e in gw.events] == list(range(len(gw.events)))


def test_pre_execution_timeout_prevents_execution() -> None:
    gw = _gateway(PreExecutionTimeout("issue_refund"))
    before = gw.state_hash()
    response = _call(gw, "issue_refund", **REFUND)
    event, entry = gw.events[-1], gw.ledger[-1]
    assert response.status is EventStatus.TIMEOUT and event.status is EventStatus.TIMEOUT
    assert entry.executed is False and entry.raw_output is None
    assert [a.stage for a in entry.fault_applications] == [FaultStage.PRE_EXECUTION]
    assert event.state is not None and not event.state.committed
    assert gw.state_hash() == before and gw.state.refunds == {}


def test_lost_ack_commits_but_delivers_timeout() -> None:
    gw = _gateway(LostAck("issue_refund"))
    before = gw.state_hash()
    response = _call(gw, "issue_refund", **REFUND)
    event, entry = gw.events[-1], gw.ledger[-1]
    # (d) delivered response: timeout
    assert response.status is EventStatus.TIMEOUT and event.status is EventStatus.TIMEOUT
    # (a) state transition: committed for real
    assert event.state is not None and event.state.committed
    assert event.state.after_hash != before and "R-0001" in gw.state.refunds
    # (b) raw result: ok;  (c) fault application recorded at POST_EXECUTION
    assert entry.executed is True and entry.raw_output["status"] == "OK"  # type: ignore[index]
    assert entry.raw_output_fp != event.response_fp
    assert [a.stage for a in entry.fault_applications] == [FaultStage.POST_EXECUTION]


def test_observable_event_hides_raw_output_and_faults() -> None:
    gw = _gateway(LostAck("issue_refund"))
    _call(gw, "issue_refund", **REFUND)
    dumped = gw.events[-1].model_dump()
    assert "raw_output" not in dumped and "fault_applications" not in dumped


def test_state_hash_helper_matches_env_hash() -> None:
    gw = _gateway()
    assert gw.state_hash() == state_hash(gw.state)
