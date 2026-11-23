"""Week 3 acceptance tests: counterfactual replay (#11-#13, #17-#19), regression (#14, #20)
and additional intervention cases (PLAN_v0.2.1 §13; REPLAY_SPEC §5.3, §5.4, §10, §14)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from agenttrace.env.support.scenario import load_scenario
from agenttrace.replay import counterfactual as cf_module
from agenttrace.replay import exact as exact_module
from agenttrace.replay.counterfactual import (
    EXE,
    OBS,
    CounterfactualResult,
    CounterfactualStatus,
    InterventionRequest,
    intervene,
    run_experiment,
)
from agenttrace.replay.exact import ReplayVerdict, replay_run
from agenttrace.replay.regression import (
    RegressionComparison,
    RegressionVerdict,
    regression_from_store,
    run_regression,
)
from agenttrace.runner import record_scenario, support_replay_context
from agenttrace.runtime.types import Decision, Observation
from agenttrace.trace.schema import (
    Boundary,
    EventStatus,
    Outcome,
    ReferenceSource,
    RunMode,
    RunRecord,
)
from agenttrace.trace.semantic import semantic_fingerprint
from agenttrace.trace.store import JsonlTraceStore
from tests import plans
from tests.replay_helpers import map_event, revalidated, tool_seqs, with_run_id

CTX = support_replay_context()
REF_TOOL = ReferenceSource.REFERENCE_TOOL
REF_POLICY = ReferenceSource.REFERENCE_POLICY
ORIGINAL = ReferenceSource.ORIGINAL


def _r6() -> RunRecord:
    """S-REF-01 (T1) + F4: wrong (archived) policy doc, limit 50 -> wrongly escalated."""
    record = record_scenario(load_scenario("T1"), fault_plan=plans.wrong_retrieval())
    assert record.footer.outcome.outcome is Outcome.FAIL
    return record


def _r4(version: str = "v1") -> RunRecord:
    """S-REF-01 + F5 lost ack on the 1st issue_refund."""
    return record_scenario(load_scenario("T1"), policy_version=version, fault_plan=plans.lost_ack())  # type: ignore[arg-type]


def _r7() -> RunRecord:
    """S-REF-01 + T0 timeout before the 1st issue_refund executes."""
    return record_scenario(load_scenario("T1"), fault_plan=plans.pre_execution_timeout())


def _completed(result: CounterfactualResult) -> RunRecord:
    assert result.status is CounterfactualStatus.COMPLETED, (result.status, result.reason)
    assert result.run is not None
    assert result.cassette_accesses_after_fence == 0
    run = result.run
    assert run.header.mode is RunMode.REPLAY_INTERVENE
    assert run.header.parent_run_id == result.original_run_id
    assert run.header.intervention is not None
    assert [e.seq for e in run.events if e.intervened] == [result.request.target_seq]
    return run


def _prefix_identical(original: RunRecord, run: RunRecord, target: int) -> None:
    def key(e: Any) -> tuple[Any, ...]:
        state = (e.state.committed, e.state.before_hash, e.state.after_hash) if e.state else None
        return e.seq, e.boundary, e.name, e.request_fp, e.response_fp, state

    before = [key(e) for e in original.events if e.seq < target]
    assert [key(e) for e in run.events if e.seq < target] == before


def _refunds(run: RunRecord) -> list[Any]:
    return [e for e in run.events if e.name == "issue_refund" and e.state and e.state.committed]


# --------------------------------------------------------------------------- #11
def test_r11_execution_replacement_repairs_and_changes_branch() -> None:
    original = _r6()
    seq = tool_seqs(original, "search_policy")[0]
    run = _completed(intervene(original, CTX, InterventionRequest(seq, EXE, REF_TOOL)))
    _prefix_identical(original, run, seq)
    assert run.footer.outcome.outcome is Outcome.PASS
    original_tools = [e.name for e in original.events if e.boundary is Boundary.TOOL]
    new_tools = [e.name for e in run.events if e.boundary is Boundary.TOOL]
    assert original_tools[-1] == "close_ticket" and "issue_refund" not in original_tools
    assert new_tools[-2:] == ["issue_refund", "close_ticket"]  # downstream branch changed
    intervention = run.header.intervention
    assert intervention is not None
    assert (intervention.intervention_type, intervention.reference_source) == (EXE, REF_TOOL)
    assert intervention.target_seq == seq and not intervention.is_placebo
    assert intervention.target_logical_key.endswith("search_policy#1")


# --------------------------------------------------------------------------- #12
def test_r12_interventions_that_do_not_repair() -> None:
    plan = plans.combine("d1+f4", plans.decoy(2, "C1"), plans.wrong_retrieval())
    original = record_scenario(load_scenario("T1"), fault_plan=plan)
    assert original.footer.outcome.outcome is Outcome.FAIL
    get_customer = tool_seqs(original, "get_customer")[0]
    assert cf_module.probe_reference(original, CTX, get_customer).outcome.value == "CONSISTENT"
    no_op = _completed(intervene(original, CTX, InterventionRequest(get_customer, EXE, REF_TOOL)))
    assert no_op.footer.outcome.outcome is Outcome.FAIL
    decoy_seq = next(
        e.seq
        for e in original.events
        if e.boundary is Boundary.DECISION
        and isinstance(e.response, dict)
        and e.response.get("summary") == "decoy"
    )
    assert cf_module.probe_reference(original, CTX, decoy_seq).outcome.value == "DEVIATES"
    experiment = run_experiment(original, CTX, InterventionRequest(decoy_seq, OBS, REF_POLICY))
    assert experiment.intervention.outcome is Outcome.FAIL
    assert experiment.placebo_valid and not experiment.repair_observed
    assert not experiment.interventional_repair


# --------------------------------------------------------------------------- #13
@pytest.mark.parametrize("itype", [EXE, OBS])
def test_r13_placebo_reproduces_original(itype: Any) -> None:
    original = _r6()
    seq = tool_seqs(original, "search_policy")[0]
    run = _completed(intervene(original, CTX, InterventionRequest(seq, itype, ORIGINAL)))
    assert run.header.intervention is not None and run.header.intervention.is_placebo
    assert run.footer.final_state_hash == original.footer.final_state_hash
    assert run.footer.outcome == original.footer.outcome
    assert [(e.name, e.request_fp, e.response_fp) for e in run.events] == [
        (e.name, e.request_fp, e.response_fp) for e in original.events
    ]


# --------------------------------------------------------------------------- #14
def test_r14_regression_against_changed_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = _r4("v1")
    assert baseline.footer.outcome.outcome is Outcome.FAIL

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("regression must never construct a cassette")

    monkeypatch.setattr(cf_module.Cassette, "__init__", forbidden)
    monkeypatch.setattr(exact_module.Cassette, "__init__", forbidden)
    report = run_regression(
        baseline.header,
        baseline.fault_plan,
        baseline.footer.outcome.outcome,
        CTX,
        policy_version="v2",
    )
    assert report.verdict is RegressionVerdict.DETERMINISTIC_PASS
    assert report.comparison is RegressionComparison.FIXED
    assert report.n == 2 and report.deterministic_reproduced
    run = report.runs[0]
    assert (
        run.header.mode is RunMode.REGRESSION and run.header.parent_run_id == baseline.header.run_id
    )
    assert len(_refunds(run)) == 1
    assert any("agent version: v1 -> v2" in d for d in report.config_differences)
    monkeypatch.undo()
    strict = exact_module.replay_strict(baseline, CTX, policy_version="v2")
    assert strict.verdict is ReplayVerdict.CONFIG_MISMATCH


# --------------------------------------------------------------------------- #17
def test_r17_observation_vs_execution_replacement_differ() -> None:
    original = _r4("v1")
    seq = tool_seqs(original, "issue_refund")[0]
    recorded = next(e for e in original.events if e.seq == seq)
    obs = _completed(intervene(original, CTX, InterventionRequest(seq, OBS, REF_TOOL)))
    exe = _completed(intervene(original, CTX, InterventionRequest(seq, EXE, REF_TOOL)))
    for run in (obs, exe):
        assert run.footer.outcome.outcome is Outcome.PASS and len(_refunds(run)) == 1
    obs_event = next(e for e in obs.events if e.seq == seq)
    exe_event = next(e for e in exe.events if e.seq == seq)
    assert obs_event.state == recorded.state  # original transition preserved
    assert obs_event.status is EventStatus.OK and recorded.status is EventStatus.TIMEOUT
    obs_ledger = next(x for x in obs.ledger if x.seq == seq)
    exe_ledger = next(x for x in exe.ledger if x.seq == seq)
    assert obs_ledger.fault_applications  # the lost-ack fault still ran underneath
    assert not exe_ledger.fault_applications  # the clean execution ran without faults
    assert exe_event.state is not None and exe_event.state.committed
    assert obs.header.intervention.intervention_type is OBS  # type: ignore[union-attr]
    assert exe.header.intervention.intervention_type is EXE  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #18
def test_r18_unsupported_interventions() -> None:
    original = _r7()
    seq = tool_seqs(original, "issue_refund")[0]
    result = intervene(original, CTX, InterventionRequest(seq, OBS, REF_TOOL))
    assert result.status is CounterfactualStatus.UNSUPPORTED
    assert result.reason == "observation_inconsistent_with_state"
    assert result.run is None and result.outcome is None
    decision_seq = seq - 1
    result = intervene(original, CTX, InterventionRequest(decision_seq, EXE, REF_TOOL))
    assert (result.status, result.reason) == (
        CounterfactualStatus.UNSUPPORTED,
        "no_state_transition_at_decision",
    )
    # EXECUTION_REPLACEMENT is faithful for the same pre-execution timeout:
    exe = _completed(intervene(original, CTX, InterventionRequest(seq, EXE, REF_TOOL)))
    assert len(_refunds(exe)) == 1


# --------------------------------------------------------------------------- #19
def test_r19_execution_replacement_placebo() -> None:
    original = _r4("v1")
    seq = tool_seqs(original, "issue_refund")[0]
    run = _completed(intervene(original, CTX, InterventionRequest(seq, EXE, ORIGINAL)))
    assert run.footer.outcome.outcome is Outcome.FAIL
    assert run.footer.final_state_hash == original.footer.final_state_hash
    assert len(_refunds(run)) == 2


# --------------------------------------------------------------------------- #20
def test_r20_regression_ignores_poisoned_cassette(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    baseline = _r4("v1")
    store.save(baseline)
    # A poisoned recording of the same scenario whose recorded decision would avoid the retry.
    close = Decision.call("close_ticket", ticket_id="TK1", resolution="REFUNDED", note="x")
    retry_decision = [e.seq for e in baseline.events if e.boundary is Boundary.DECISION][4]
    poisoned = map_event(
        baseline, retry_decision, lambda e: revalidated(e, response=close.model_dump(mode="json"))
    )
    store.save(with_run_id(poisoned, baseline.header.run_id + "-poisoned"))
    assert len(store.list_run_ids()) == 2
    v1 = regression_from_store(store, baseline.header.run_id, CTX, policy_version="v1")
    v2 = regression_from_store(store, baseline.header.run_id, CTX, policy_version="v2")
    assert v1.verdict is RegressionVerdict.DETERMINISTIC_FAIL
    assert v1.comparison is RegressionComparison.STILL_FAILING
    assert all(len(_refunds(r)) == 2 for r in v1.runs)  # recorded decisions were not reused
    assert v2.verdict is RegressionVerdict.DETERMINISTIC_PASS
    assert v2.comparison is RegressionComparison.FIXED


# --------------------------------------------------------------------------- extra cases
@pytest.mark.parametrize("position", ["first", "middle", "final"])
def test_intervention_at_first_middle_final_boundary(position: str) -> None:
    original = _r6()
    decisions = [e.seq for e in original.events if e.boundary is Boundary.DECISION]
    seq = {"first": decisions[0], "middle": decisions[len(decisions) // 2], "final": decisions[-1]}[
        position
    ]
    run = _completed(intervene(original, CTX, InterventionRequest(seq, OBS, REF_POLICY)))
    _prefix_identical(original, run, seq)
    # References equal the recorded decisions here (only the retrieval was faulty).
    assert run.footer.outcome == original.footer.outcome
    assert run.footer.final_state_hash == original.footer.final_state_hash


def test_missing_trusted_reference_is_unsupported() -> None:
    original = _r6()
    ctx = dataclasses.replace(CTX, reference_decider=lambda _p, _v: None)
    seq = next(e.seq for e in original.events if e.boundary is Boundary.DECISION)
    result = intervene(original, ctx, InterventionRequest(seq, OBS, REF_POLICY))
    assert (result.status, result.reason) == (
        CounterfactualStatus.UNSUPPORTED,
        "no_trusted_reference",
    )
    assert cf_module.probe_reference(original, ctx, seq).reason == "no_trusted_reference"


@pytest.mark.parametrize(
    ("seq", "itype", "source", "reason"),
    [
        (0, EXE, REF_TOOL, "target_not_boundary"),  # AGENT_STEP span
        (999, OBS, REF_TOOL, "target_not_boundary"),  # out of range
        (1, OBS, REF_TOOL, "reference_not_applicable_to_boundary"),  # tool reference at decision
        (2, OBS, REF_POLICY, "reference_not_applicable_to_boundary"),  # policy ref at tool
        (2, OBS, ReferenceSource.INJECTION_CLEAN_VALUE, "privileged_reference_denied"),
    ],
)
def test_invalid_requests_are_rejected_before_execution(
    seq: int, itype: Any, source: Any, reason: str
) -> None:
    original = _r6()
    result = intervene(original, CTX, InterventionRequest(seq, itype, source))
    assert (result.status, result.reason) == (CounterfactualStatus.UNSUPPORTED, reason)
    assert result.run is None


def test_injection_clean_value_requires_privilege_and_repairs() -> None:
    original = _r6()
    seq = tool_seqs(original, "search_policy")[0]
    request = InterventionRequest(seq, OBS, ReferenceSource.INJECTION_CLEAN_VALUE)
    run = _completed(intervene(original, CTX, request, allow_privileged=True))
    assert run.footer.outcome.outcome is Outcome.PASS
    exe = intervene(
        original,
        CTX,
        InterventionRequest(seq, EXE, ReferenceSource.INJECTION_CLEAN_VALUE),
        allow_privileged=True,
    )
    assert exe.reason == "reference_not_applicable_to_type"


def test_prefix_divergence_is_invalid_counterfactual() -> None:
    original = _r6()
    seq = tool_seqs(original, "get_order")[0]
    tampered = map_event(
        original,
        seq,
        lambda e: revalidated(e, request={"tool": "get_order", "args": {"order_id": "O9"}}),
    )
    target = tool_seqs(original, "search_policy")[0]
    result = intervene(tampered, CTX, InterventionRequest(target, EXE, REF_TOOL))
    assert result.status is CounterfactualStatus.INVALID_COUNTERFACTUAL
    assert result.reason == "prefix_diverged" and result.divergence is not None


def test_state_isolation_across_experiments() -> None:
    original = _r6()
    before = semantic_fingerprint(original)
    seq = tool_seqs(original, "search_policy")[0]
    signatures = set()
    for _ in range(5):
        for request in (
            InterventionRequest(seq, EXE, REF_TOOL),
            InterventionRequest(seq, OBS, REF_TOOL),
        ):
            run = _completed(intervene(original, CTX, request))
            signatures.add(
                (request.intervention_type, run.footer.final_state_hash, run.footer.outcome.outcome)
            )
    assert semantic_fingerprint(original) == before
    assert len(signatures) == 2  # deterministic per type; no leakage between experiments


def test_multiple_faults_not_isolated_by_single_step() -> None:
    plan = plans.combine(
        "f2+f4",
        plans.wrong_argument(2, "get_order", "order_id", "replace", "O6A"),
        plans.wrong_retrieval("T6"),
    )
    original = record_scenario(load_scenario("T6"), fault_plan=plan)
    assert original.footer.outcome.outcome is Outcome.FAIL
    decision = [e.seq for e in original.events if e.boundary is Boundary.DECISION][1]
    retrieval = tool_seqs(original, "search_policy")[0]
    for request in (
        InterventionRequest(decision, OBS, REF_POLICY),
        InterventionRequest(retrieval, EXE, REF_TOOL),
    ):
        experiment = run_experiment(original, CTX, request)
        assert experiment.placebo_valid
        assert not experiment.repair_observed  # each fault alone is sufficient to fail


def test_live_suffix_uses_the_real_policy() -> None:
    calls: list[int] = []
    base = CTX.make_policy

    class Spy:
        def __init__(self, inner: Any) -> None:
            self.inner = inner
            self.policy_id, self.policy_version = inner.policy_id, inner.policy_version
            self.source_hash, self.deterministic = inner.source_hash, inner.deterministic

        def decide(self, task: Any, history: Sequence[Observation]) -> Decision:
            calls.append(len(history))
            return self.inner.decide(task, history)

    ctx = dataclasses.replace(CTX, make_policy=lambda p, v: Spy(base(p, v)))
    original = _r6()
    seq = tool_seqs(original, "search_policy")[0]
    _completed(intervene(original, ctx, InterventionRequest(seq, EXE, REF_TOOL)))
    assert calls and min(calls) >= 3  # only called after the target (3 tool observations)


def test_regression_drops_decision_faults() -> None:
    plan = plans.wrong_tool(4, "close_ticket", {"ticket_id": "TK1", "resolution": "DENIED"})
    baseline = record_scenario(load_scenario("T1"), fault_plan=plan)
    assert baseline.footer.outcome.outcome is Outcome.FAIL
    report = run_regression(
        baseline.header, baseline.fault_plan, Outcome.FAIL, CTX, policy_version="v1"
    )
    assert report.dropped_decision_faults == ("wrong_tool-d4",)
    assert report.fixture_hash is None and report.comparison is RegressionComparison.FIXED


def test_regression_unknown_policy_is_config_error() -> None:
    baseline = _r4()
    report = run_regression(
        baseline.header, baseline.fault_plan, Outcome.FAIL, CTX, policy_version="v9"
    )
    assert report.verdict is RegressionVerdict.CONFIG_ERROR and not report.runs


def test_strict_replay_still_verified_after_week3(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    for record in (_r6(), _r4(), _r7()):
        store.save(record)
        assert replay_run(store, record.header.run_id, CTX).verdict is ReplayVerdict.VERIFIED
