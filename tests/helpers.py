"""Hand-built minimal trace records for schema/store tests (independent of the runtime)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.integrity import compute_chain_root
from agenttrace.trace.schema import (
    AgentRef,
    Boundary,
    DeltaOp,
    Event,
    EventStatus,
    Integrity,
    LedgerEntry,
    OracleRef,
    Outcome,
    OutcomeRecord,
    RunFooter,
    RunHeader,
    RunMode,
    RunRecord,
    RunStatus,
    ScenarioRef,
    StateTransition,
    Totals,
    compute_config_fingerprint,
)

T0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def make_header(run_id: str = "run-test-1", **overrides: Any) -> RunHeader:
    fields: dict[str, Any] = {
        "schema_version": "1.0",
        "scenario": ScenarioRef(id="T1", version="1", initial_state_hash="sha256:" + "0" * 64),
        "agent": AgentRef(
            policy_id="scripted", policy_version="v1", source_hash="sha256:" + "1" * 64
        ),
        "tool_manifest_hash": "sha256:" + "2" * 64,
        "fault_plan_hash": None,
        "oracle": OracleRef(id="support-oracle", version="1.0"),
        "max_steps": 12,
    }
    fields.update(overrides)
    return RunHeader(
        run_id=run_id,
        mode=RunMode.RECORD,
        config_fingerprint=compute_config_fingerprint(**fields),
        started_at=T0,
        agenttrace_version="0.0.1",
        **fields,
    )


def make_record(run_id: str = "run-test-1") -> RunRecord:
    request = {"tool": "issue_refund", "args": {"order_id": "O1", "amount": "80"}}
    response = {"status": "OK", "data": {"refund_id": "R-0001"}, "error": None}
    decision = {
        "kind": "tool_call",
        "tool": "issue_refund",
        "args": request["args"],
        "summary": None,
    }
    dec_request = {"policy_id": "scripted", "policy_version": "v1", "history_fp": fingerprint([])}
    events = (
        Event(
            span_id="s0",
            run_id=run_id,
            seq=0,
            step_index=0,
            logical_key="0:AGENT_STEP:step#1",
            boundary=Boundary.AGENT_STEP,
            name="step",
            status=EventStatus.OK,
        ),
        Event(
            span_id="s1",
            parent_span_id="s0",
            run_id=run_id,
            seq=1,
            step_index=0,
            logical_key="0:DECISION:decide#1",
            boundary=Boundary.DECISION,
            name="decide",
            status=EventStatus.OK,
            request=dec_request,
            request_fp=fingerprint(dec_request),
            response=decision,
            response_fp=fingerprint(decision),
        ),
        Event(
            span_id="s2",
            parent_span_id="s0",
            run_id=run_id,
            seq=2,
            step_index=0,
            logical_key="0:TOOL:issue_refund#1",
            boundary=Boundary.TOOL,
            name="issue_refund",
            status=EventStatus.OK,
            request=request,
            request_fp=fingerprint(request),
            response=response,
            response_fp=fingerprint(response),
            attempt=1,
            state=StateTransition(
                before_hash="sha256:" + "a" * 64,
                after_hash="sha256:" + "b" * 64,
                committed=True,
                delta=(DeltaOp(op="add", path="/refunds/R-0001", new={"amount": "80"}),),
            ),
        ),
    )
    ledger = (
        LedgerEntry(
            seq=1,
            boundary=Boundary.DECISION,
            raw_output=decision,
            raw_output_fp=fingerprint(decision),
        ),
        LedgerEntry(
            seq=2,
            boundary=Boundary.TOOL,
            executed=True,
            raw_output=response,
            raw_output_fp=fingerprint(response),
        ),
    )
    footer = RunFooter(
        status=RunStatus.COMPLETED,
        outcome=OutcomeRecord(outcome=Outcome.PASS),
        final_state_hash="sha256:" + "b" * 64,
        totals=Totals(events=3, decisions=1, tool_calls=1, steps=1),
        ended_at=T0,
        wall_ms=5,
        integrity=Integrity(
            event_count=3, ledger_count=2, chain_root=compute_chain_root(events, ledger)
        ),
    )
    return RunRecord(header=make_header(run_id), events=events, ledger=ledger, footer=footer)
