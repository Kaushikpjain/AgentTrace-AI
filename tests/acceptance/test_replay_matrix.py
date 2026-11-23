"""Replay acceptance tests (PLAN_v0.2.1 section 13; REPLAY_SPEC section 13).

Week 2 scope: #1-#10, #15, #16, #21 (REPLAY_STRICT) plus corrupted-cassette and
changed-configuration cases. #11-#14 and #17-#20 are Week 3.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pytest

from agenttrace.env.base import ToolResult, ToolSpec
from agenttrace.env.support.models import SupportState
from agenttrace.env.support.scenario import TaskSpec, list_scenario_ids, load_scenario
from agenttrace.env.support.tools import SUPPORT_TOOLS_BY_NAME, IssueRefundArgs
from agenttrace.env.support.tools import get_order as real_get_order
from agenttrace.env.support.tools import issue_refund as real_issue_refund
from agenttrace.policies.support_scripted import ScriptedSupportPolicy
from agenttrace.replay.exact import ReplayReport, ReplayVerdict, replay_strict
from agenttrace.runner import episode_for, record_scenario, support_replay_context
from agenttrace.runtime.loop import run_episode
from agenttrace.runtime.types import Decision, Observation
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    AgentRef,
    Boundary,
    DivergenceKind,
    EventStatus,
    FaultStage,
    Outcome,
    OutcomeRecord,
    RunMode,
    RunRecord,
    RunStatus,
)
from agenttrace.trace.semantic import semantic_fingerprint
from tests import plans
from tests.replay_helpers import drop_events, map_event, map_ledger, revalidated, tool_seqs

CTX = support_replay_context()


def _replay(record: RunRecord, **kwargs: Any) -> ReplayReport:
    return replay_strict(record, CTX, **kwargs)


def _assert_verified(report: ReplayReport, original: RunRecord) -> RunRecord:
    assert report.verdict is ReplayVerdict.VERIFIED, report.divergence
    assert report.divergence is None and report.policy_calls == 0
    assert report.fidelity is not None and report.fidelity.exact
    assert report.cassette_consumed == report.cassette_entries
    replay = report.replay
    assert replay is not None
    assert replay.header.mode is RunMode.REPLAY_STRICT
    assert replay.header.parent_run_id == original.header.run_id
    assert replay.header.config_fingerprint == original.header.config_fingerprint
    assert replay.footer.final_state_hash == original.footer.final_state_hash
    assert replay.footer.status is original.footer.status
    assert replay.footer.outcome == original.footer.outcome
    return replay


def _assert_diverged(report: ReplayReport, kind: DivergenceKind, seq: int) -> RunRecord:
    assert report.verdict is ReplayVerdict.DIVERGED
    assert report.divergence is not None
    assert (report.divergence.kind, report.divergence.seq) == (kind, seq), report.divergence
    assert report.policy_calls == 0
    replay = report.replay
    assert replay is not None and replay.footer.status is RunStatus.DIVERGED
    assert replay.footer.divergence == report.divergence
    assert replay.events[-1].seq <= seq  # nothing executed past the divergence
    return replay


def _tool_event(record: RunRecord, name: str, nth: int = 0) -> Any:
    return [e for e in record.events if e.boundary is Boundary.TOOL and e.name == name][nth]


def _ledger(record: RunRecord, seq: int) -> Any:
    return next(entry for entry in record.ledger if entry.seq == seq)


# --------------------------------------------------------------------------- #1, #2
def test_r01_exact_replay_of_clean_run(monkeypatch: pytest.MonkeyPatch) -> None:
    original = record_scenario(load_scenario("T1"))
    assert original.footer.outcome.outcome is Outcome.PASS

    def forbidden(*_: object) -> Decision:
        raise AssertionError("policy invoked during strict replay")

    monkeypatch.setattr(ScriptedSupportPolicy, "decide", forbidden)
    replay = _assert_verified(_replay(original), original)
    tools = [e.name for e in replay.events if e.boundary is Boundary.TOOL]
    assert tools[-1] == "close_ticket"


def test_r02_exact_replay_of_failed_run() -> None:
    plan = plans.corrupt_output("get_order", ["data", "total"], "800.00")
    original = record_scenario(load_scenario("T1"), fault_plan=plan)
    assert original.footer.outcome.outcome is Outcome.FAIL
    replay = _assert_verified(_replay(original), original)
    assert [c.clause_id for c in replay.footer.outcome.violated_clauses] == [
        c.clause_id for c in original.footer.outcome.violated_clauses
    ]
    corrupted = _ledger(replay, _tool_event(replay, "get_order").seq)
    assert [a.stage for a in corrupted.fault_applications] == [FaultStage.POST_EXECUTION]


# --------------------------------------------------------------------------- #3
def test_r03_missing_cassette_entry_middle() -> None:
    original = record_scenario(load_scenario("T1"))
    missing = tool_seqs(original, "get_order")[0]
    tampered = drop_events(original, {missing})
    replay = _assert_diverged(_replay(tampered), DivergenceKind.BOUNDARY, missing)
    assert "get_order" not in [e.name for e in replay.events]  # never executed


def test_r03b_truncated_cassette() -> None:
    original = record_scenario(load_scenario("T1"))
    last_step, last_decision = original.events[-2].seq, original.events[-1].seq
    tampered = drop_events(original, {last_step, last_decision})
    _assert_diverged(_replay(tampered), DivergenceKind.MISSING_EVENT, last_decision)


def test_r03c_unconsumed_cassette_entries_are_truncation() -> None:
    """A replay loop that ends while recorded entries remain must report TRUNCATED."""
    original = record_scenario(load_scenario("T1"))  # 6 steps recorded
    short_loop = dataclasses.replace(CTX, build_episode=_with_max_steps(3))
    report = replay_strict(original, short_loop)
    first_unconsumed = [e.seq for e in original.events if e.boundary is not Boundary.AGENT_STEP][6]
    _assert_diverged(report, DivergenceKind.TRUNCATED, first_unconsumed)
    assert report.cassette_consumed == 6


def _with_max_steps(max_steps: int) -> Any:
    def build(header: Any, plan: Any) -> Any:
        return episode_for(load_scenario(header.scenario.id), fault_plan=plan, max_steps=max_steps)

    return build


# --------------------------------------------------------------------------- #4
def test_r04_request_mismatch() -> None:
    original = record_scenario(load_scenario("T1"))
    seq = tool_seqs(original, "get_order")[0]
    tampered_request = {"tool": "get_order", "args": {"order_id": "O9"}}
    tampered = map_event(original, seq, lambda e: revalidated(e, request=tampered_request))
    replay = _assert_diverged(_replay(tampered), DivergenceKind.REQUEST, seq)
    assert replay.footer.divergence is not None
    assert replay.footer.divergence.expected_fp == fingerprint(tampered_request)
    assert replay.footer.divergence.actual_fp == _tool_event(original, "get_order").request_fp


def test_r04b_changed_tool_arguments_in_decision() -> None:
    """The recorded decision asks for different args than the recorded tool call used."""
    original = record_scenario(load_scenario("T6"))
    tool_seq = tool_seqs(original, "get_order")[0]
    decision_seq = tool_seq - 1
    wrong = Decision.call("get_order", order_id="O6A")  # recorded tool call used O6B
    tampered = map_event(
        original, decision_seq, lambda e: revalidated(e, response=wrong.model_dump(mode="json"))
    )
    _assert_diverged(_replay(tampered), DivergenceKind.REQUEST, tool_seq)


# --------------------------------------------------------------------------- #5
def _get_order_with_extra_field(state: SupportState, args: Any) -> ToolResult:
    result = real_get_order(state, args)
    assert result.data is not None
    return ToolResult.success({**result.data, "loyalty_points": 7})


def test_r05_changed_tool_implementation_same_manifest() -> None:
    original = record_scenario(load_scenario("T1"))
    tools = dict(SUPPORT_TOOLS_BY_NAME)
    spec = tools["get_order"]
    tools["get_order"] = ToolSpec(
        spec.name, spec.args_model, spec.mutating, _get_order_with_extra_field
    )
    ctx = support_replay_context(tools=tools)  # manifest hash deliberately unchanged
    seq = tool_seqs(original, "get_order")[0]
    report = replay_strict(original, ctx)
    _assert_diverged(report, DivergenceKind.RAW_RESULT, seq)


def test_r05b_changed_tool_manifest_is_config_mismatch() -> None:
    original = record_scenario(load_scenario("T1"))
    ctx = support_replay_context(tool_manifest_hash="sha256:" + "f" * 64)
    report = replay_strict(original, ctx)
    assert report.verdict is ReplayVerdict.CONFIG_MISMATCH and report.replay is None
    assert any(m.startswith("tools:") for m in report.config.mismatches)


# --------------------------------------------------------------------------- #6
def test_r06_changed_downstream_branch() -> None:
    original = record_scenario(load_scenario("T2"))  # escalates: no refund
    close_seq = tool_seqs(original, "close_ticket")[0]
    decision_seq = close_seq - 1
    refund = Decision.call("issue_refund", order_id="O2", amount="150")
    tampered = map_event(
        original, decision_seq, lambda e: revalidated(e, response=refund.model_dump(mode="json"))
    )
    report = _replay(tampered)
    replay = _assert_diverged(report, DivergenceKind.NAME, close_seq)
    assert all(e.name != "issue_refund" for e in replay.events if e.boundary is Boundary.TOOL)
    assert report.cassette_consumed == report.cassette_entries - 2  # nothing served after


# --------------------------------------------------------------------------- #7
def _refund_with_extra_audit(state: SupportState, args: IssueRefundArgs) -> ToolResult:
    result = real_issue_refund(state, args)
    state.next_refund_number += 10  # different state, identical raw result
    return result


def test_r07_state_hash_divergence() -> None:
    original = record_scenario(load_scenario("T1"))
    tools = dict(SUPPORT_TOOLS_BY_NAME)
    spec = tools["issue_refund"]
    tools["issue_refund"] = ToolSpec(spec.name, spec.args_model, True, _refund_with_extra_audit)
    report = replay_strict(original, support_replay_context(tools=tools))
    _assert_diverged(report, DivergenceKind.STATE, tool_seqs(original, "issue_refund")[0])


# --------------------------------------------------------------------------- #8
class RepeatReader:
    """Test policy: repeated same-name reads with different and identical arguments."""

    policy_id = "test-repeat-reader"
    policy_version = "1"
    source_hash = "sha256:" + "9" * 64
    deterministic = True
    PLAN = (
        ("get_order", {"order_id": "O6A"}),
        ("get_order", {"order_id": "O6B"}),
        ("get_customer", {"customer_id": "C6"}),
        ("get_customer", {"customer_id": "C6"}),
    )

    def decide(self, task: TaskSpec, history: Sequence[Observation]) -> Decision:
        if len(history) < len(self.PLAN):
            tool, args = self.PLAN[len(history)]
            return Decision.call(tool, **args)
        return Decision.final("done")


def _repeat_ctx() -> Any:
    agent = AgentRef(
        policy_id=RepeatReader.policy_id,
        policy_version=RepeatReader.policy_version,
        source_hash=RepeatReader.source_hash,
    )
    return dataclasses.replace(
        CTX, current_agent_ref=lambda pid, v: agent if pid == agent.policy_id else None
    )


def test_r08_repeated_tool_calls_matched_positionally() -> None:
    original = run_episode(episode_for(load_scenario("T6")), RepeatReader())
    orders = [e for e in original.events if e.name == "get_order"]
    customers = [e for e in original.events if e.name == "get_customer"]
    assert orders[0].response_fp != orders[1].response_fp
    assert customers[0].response_fp == customers[1].response_fp
    assert [c.attempt for c in customers] == [1, 2]
    report = replay_strict(original, _repeat_ctx())
    replay = report.replay
    assert report.verdict is ReplayVerdict.VERIFIED and replay is not None
    replayed = [e for e in replay.events if e.name == "get_order"]
    assert [e.response_fp for e in replayed] == [e.response_fp for e in orders]

    # Swap the two recorded get_order calls: positional matching must reject it.
    first, second = orders
    swapped = map_event(
        original,
        first.seq,
        lambda e: revalidated(e, request=second.request, response=second.response),
    )
    swapped = map_event(
        swapped,
        second.seq,
        lambda e: revalidated(e, request=first.request, response=first.response),
    )
    report = replay_strict(swapped, _repeat_ctx())
    assert report.verdict is ReplayVerdict.DIVERGED and report.divergence is not None
    assert (report.divergence.kind, report.divergence.seq) == (DivergenceKind.REQUEST, first.seq)


# --------------------------------------------------------------------------- #9
def test_r09_lost_ack_duplicate_retry_replays_exactly() -> None:
    original = record_scenario(
        load_scenario("T1"), policy_version="v1", fault_plan=plans.lost_ack()
    )
    assert original.footer.outcome.outcome is Outcome.FAIL
    replay = _assert_verified(_replay(original), original)
    refunds = [e for e in replay.events if e.name == "issue_refund"]
    assert len(refunds) == 2
    first = refunds[0]
    assert first.status is EventStatus.TIMEOUT
    assert first.state is not None and first.state.committed
    assert first.state.after_hash != first.state.before_hash
    assert _ledger(replay, first.seq).raw_output["status"] == "OK"
    assert refunds[1].state is not None and refunds[1].state.committed  # the duplicate


# --------------------------------------------------------------------------- #10
def test_r10_early_termination_max_steps() -> None:
    original = record_scenario(load_scenario("T1"), max_steps=3)
    assert original.footer.status is RunStatus.MAX_STEPS
    replay = _assert_verified(_replay(original), original)
    assert replay.footer.status is RunStatus.MAX_STEPS
    assert len(replay.events) == len(original.events)


# --------------------------------------------------------------------------- #15
def test_r15_repeated_execution_without_state_leakage() -> None:
    scenarios = {sid: load_scenario(sid) for sid in list_scenario_ids()}
    initial_hashes = {sid: s.initial_state_hash() for sid, s in scenarios.items()}
    recordings = {sid: record_scenario(s) for sid, s in scenarios.items()}
    baseline = {sid: semantic_fingerprint(r) for sid, r in recordings.items()}
    for _ in range(5):
        for sid, scenario in scenarios.items():
            assert semantic_fingerprint(record_scenario(scenario)) == baseline[sid]
            _assert_verified(_replay(recordings[sid]), recordings[sid])
    for sid, scenario in scenarios.items():
        assert scenario.initial_state_hash() == initial_hashes[sid]


# --------------------------------------------------------------------------- #16
def test_r16_pre_execution_timeout_replays_exactly() -> None:
    original = record_scenario(
        load_scenario("T1"), policy_version="v1", fault_plan=plans.pre_execution_timeout()
    )
    assert original.footer.outcome.outcome is Outcome.PASS
    replay = _assert_verified(_replay(original), original)
    first, second = [e for e in replay.events if e.name == "issue_refund"]
    entry = _ledger(replay, first.seq)
    assert first.status is EventStatus.TIMEOUT
    assert entry.executed is False and entry.raw_output is None
    assert [a.stage for a in entry.fault_applications] == [FaultStage.PRE_EXECUTION]
    assert first.state is not None and not first.state.committed
    assert first.state.before_hash == first.state.after_hash
    assert second.state is not None and second.state.committed


# --------------------------------------------------------------------------- #21
def test_r21_idempotent_retry_replays_exactly() -> None:
    original = record_scenario(
        load_scenario("T1"), policy_version="v2", fault_plan=plans.lost_ack()
    )
    assert original.footer.outcome.outcome is Outcome.PASS
    replay = _assert_verified(_replay(original), original)
    first, second = [e for e in replay.events if e.name == "issue_refund"]
    assert first.status is EventStatus.TIMEOUT and first.state.committed  # type: ignore[union-attr]
    assert _ledger(replay, second.seq).executed is True
    assert second.state is not None and not second.state.committed
    assert second.response["data"]["refund_id"] == "R-0001"  # type: ignore[index]
    assert second.response["data"]["idempotent_replay"] is True  # type: ignore[index]


# --------------------------------------------------------------------------- config and outcome
def test_changed_policy_version_is_config_mismatch() -> None:
    original = record_scenario(load_scenario("T1"), policy_version="v1")
    report = _replay(original, policy_version="v2")
    assert report.verdict is ReplayVerdict.CONFIG_MISMATCH and report.replay is None
    assert any("policy version v2" in m for m in report.config.mismatches)


def test_changed_policy_source_is_config_mismatch() -> None:
    original = record_scenario(load_scenario("T1"))
    changed = AgentRef(
        policy_id=original.header.agent.policy_id,
        policy_version=original.header.agent.policy_version,
        source_hash="sha256:" + "0" * 64,
    )
    ctx = dataclasses.replace(CTX, current_agent_ref=lambda pid, v: changed)
    report = replay_strict(original, ctx)
    assert report.verdict is ReplayVerdict.CONFIG_MISMATCH
    assert any("source code changed" in m for m in report.config.mismatches)


def test_unknown_scenario_is_config_mismatch() -> None:
    original = record_scenario(load_scenario("T1"))
    ctx = dataclasses.replace(CTX, current_scenario_ref=lambda sid: None)
    assert replay_strict(original, ctx).verdict is ReplayVerdict.CONFIG_MISMATCH


def test_outcome_divergence_detected() -> None:
    original = record_scenario(load_scenario("T1"))
    base_build = CTX.build_episode

    def failing_oracle(header: Any, plan: Any) -> Any:
        spec = base_build(header, plan)
        return dataclasses.replace(spec, oracle=lambda state: OutcomeRecord(outcome=Outcome.FAIL))

    report = replay_strict(original, dataclasses.replace(CTX, build_episode=failing_oracle))
    assert report.verdict is ReplayVerdict.DIVERGED
    assert report.divergence is not None and report.divergence.kind is DivergenceKind.OUTCOME
    assert report.fidelity is not None and not report.fidelity.outcome_equal


def test_diverged_replay_is_not_evaluated() -> None:
    original = record_scenario(load_scenario("T1"))
    seq = tool_seqs(original, "get_customer")[0]
    tampered = map_ledger(
        original,
        seq,
        lambda entry: revalidated(
            entry, raw_output={"status": "OK", "data": {"customer_id": "C1"}, "error": None}
        ),
    )
    report = _replay(tampered)
    replay = _assert_diverged(report, DivergenceKind.RAW_RESULT, seq)
    assert replay.footer.outcome.outcome is Outcome.NOT_EVALUATED
    assert report.fidelity is not None and not report.fidelity.exact


def test_money_scale_does_not_affect_replay() -> None:
    assert fingerprint({"a": Decimal("80.00")}) == fingerprint({"a": Decimal("80")})
