"""REPLAY_INTERVENE: typed single-step interventions with placebo controls.

Authoritative semantics: docs/REPLAY_SPEC.md sections 5.3, 10 and 14.

- The prefix (seq < target) is replayed strictly and verified (REPLAY_STRICT rules).
- At the target the declared replacement is applied:
  OBSERVATION_REPLACEMENT keeps the original execution and state transition and replaces only
  the delivered value; EXECUTION_REPLACEMENT replaces the execution itself (fault layer
  disabled for the reference, enabled for the placebo).
- Immediately after the target the cassette is closed (fence); the downstream workflow runs
  live: the real policy decides and sandbox tools execute with the recorded fault plan.
- Unsupported or unfaithful requests return an explicit UNSUPPORTED result, never an outcome.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from agenttrace.env.base import ToolSpec
from agenttrace.replay.cassette import Cassette, CassetteEntry
from agenttrace.replay.exact import (
    LiveCallAttempted,
    ReferenceDecider,
    ReplayContext,
    ReplayPolicyGuard,
    StrictReplayGateway,
    check_config,
)
from agenttrace.runtime.faults import DecisionContext, FaultHook, NoFaults, ToolContext
from agenttrace.runtime.gateway import BoundaryGateway, ToolExecution
from agenttrace.runtime.loop import run_episode
from agenttrace.runtime.types import Decision, Observation, Policy, ToolResponse
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    Boundary,
    Divergence,
    Event,
    FaultApplication,
    Intervention,
    InterventionType,
    LedgerEntry,
    Outcome,
    ReferenceSource,
    RunMode,
    RunRecord,
    RunStatus,
)

OBS = InterventionType.OBSERVATION_REPLACEMENT
EXE = InterventionType.EXECUTION_REPLACEMENT


class CounterfactualStatus(StrEnum):
    COMPLETED = "COMPLETED"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID_COUNTERFACTUAL = "INVALID_COUNTERFACTUAL"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"


class InterventionUnsupported(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class InterventionRequest:
    target_seq: int
    intervention_type: InterventionType
    reference_source: ReferenceSource
    expected_semantics: str = ""

    @property
    def is_placebo(self) -> bool:
        return self.reference_source is ReferenceSource.ORIGINAL

    def placebo(self) -> InterventionRequest:
        return InterventionRequest(
            self.target_seq,
            self.intervention_type,
            ReferenceSource.ORIGINAL,
            f"placebo for {self.intervention_type.value}: original value/execution",
        )


@dataclass(frozen=True)
class CounterfactualResult:
    status: CounterfactualStatus
    request: InterventionRequest
    original_run_id: str
    original_outcome: Outcome
    reason: str | None = None
    run: RunRecord | None = None
    divergence: Divergence | None = None
    cassette_accesses_after_fence: int = 0

    @property
    def outcome(self) -> Outcome | None:
        if self.status is not CounterfactualStatus.COMPLETED or self.run is None:
            return None
        return self.run.footer.outcome.outcome


# ---------------------------------------------------------------- prechecks
def _target_entry(original: RunRecord, seq: int) -> CassetteEntry | None:
    events = {e.seq: e for e in original.events}
    event = events.get(seq)
    if event is None or event.boundary not in (Boundary.DECISION, Boundary.TOOL):
        return None
    ledger = next(entry for entry in original.ledger if entry.seq == seq)
    return CassetteEntry(event, ledger)


def precheck(
    original: RunRecord,
    request: InterventionRequest,
    ctx: ReplayContext,
    *,
    allow_privileged: bool = False,
) -> str | None:
    """Return an UNSUPPORTED reason, or None if the request can be executed faithfully."""
    target = _target_entry(original, request.target_seq)
    if target is None:
        return "target_not_boundary"
    boundary = target.event.boundary
    itype, source = request.intervention_type, request.reference_source
    if boundary is Boundary.DECISION and itype is EXE:
        return "no_state_transition_at_decision"
    if source is ReferenceSource.REFERENCE_TOOL and boundary is not Boundary.TOOL:
        return "reference_not_applicable_to_boundary"
    if source is ReferenceSource.REFERENCE_POLICY:
        if boundary is not Boundary.DECISION:
            return "reference_not_applicable_to_boundary"
        agent = original.header.agent
        if ctx.reference_decider(agent.policy_id, agent.policy_version) is None:
            return "no_trusted_reference"
    if source is ReferenceSource.INJECTION_CLEAN_VALUE:
        if not allow_privileged:
            return "privileged_reference_denied"
        if itype is not OBS:
            return "reference_not_applicable_to_type"
        if target.ledger.raw_output is None:
            return "no_trusted_reference"
    agent = original.header.agent
    if ctx.make_policy(agent.policy_id, agent.policy_version) is None:
        return "no_live_policy"
    return None


# ---------------------------------------------------------------- gateway
class CounterfactualGateway[S: BaseModel](StrictReplayGateway[S]):
    def __init__(
        self,
        *,
        run_id: str,
        state: S,
        tools: Mapping[str, ToolSpec[Any]],
        fault_hook: FaultHook,
        cassette: Cassette,
        request: InterventionRequest,
        decider: ReferenceDecider | None,
    ) -> None:
        super().__init__(
            run_id=run_id, state=state, tools=tools, fault_hook=fault_hook, cassette=cassette
        )
        self._request = request
        self._decider = decider
        self._target = request.target_seq
        self._pre_state: S | None = None
        self._target_entry: CassetteEntry | None = None
        self.fenced = False
        self.accesses_at_fence = 0

    def _fence(self) -> None:
        self._cassette.close()
        self.fenced = True
        self.accesses_at_fence = self._cassette.accesses

    def _is_intervened(self, seq: int) -> bool:
        return seq == self._target

    # decisions
    def _produce_decision[T: BaseModel](
        self,
        ctx: DecisionContext,
        request_fp: str,
        policy: Policy[T],
        task: T,
        history: Sequence[Observation],
    ) -> tuple[Decision, Decision, list[FaultApplication]]:
        if self.fenced:  # live suffix: real policy + recorded fault plan
            return BoundaryGateway._produce_decision(self, ctx, request_fp, policy, task, history)
        if ctx.seq != self._target:
            return super()._produce_decision(ctx, request_fp, policy, task, history)
        entry = self._cassette.expect(ctx.seq, Boundary.DECISION, "decide", request_fp)
        raw = Decision.model_validate(entry.ledger.raw_output)
        source = self._request.reference_source
        if source is ReferenceSource.ORIGINAL:
            delivered = Decision.model_validate(entry.event.response)
        elif source is ReferenceSource.INJECTION_CLEAN_VALUE:
            delivered = raw
        else:  # REFERENCE_POLICY (precheck guarantees a decider)
            assert self._decider is not None
            delivered = self._decider.reference_decision(task, history)
        self._fence()
        return raw, delivered, []  # the delivered value is the intervention, not a fault

    # tools
    def _before_tool(self, seq: int, name: str, request_fp: str) -> None:
        if self.fenced:
            return
        if seq != self._target:
            super()._before_tool(seq, name, request_fp)
            return
        self._target_entry = self._cassette.expect(seq, Boundary.TOOL, name, request_fp)
        self._pre_state = self.state.model_copy(deep=True)

    def _tool_hook(self, seq: int) -> FaultHook:
        if (
            seq == self._target
            and self._request.intervention_type is EXE
            and self._request.reference_source is ReferenceSource.REFERENCE_TOOL
        ):
            return NoFaults()  # trusted clean execution for this event only
        return self._hook

    def _transform_delivered(
        self, seq: int, ctx: ToolContext, delivered: ToolResponse, execution: ToolExecution[S]
    ) -> ToolResponse:
        if seq != self._target or self._request.intervention_type is not OBS:
            return delivered
        entry = self._target_entry
        assert entry is not None and self._pre_state is not None
        source = self._request.reference_source
        if source is ReferenceSource.ORIGINAL:
            return ToolResponse.model_validate(entry.event.response)
        if source is ReferenceSource.INJECTION_CLEAN_VALUE:
            return ToolResponse.model_validate(entry.ledger.raw_output)
        reference = self.lifecycle(ctx.tool, ctx.args, ctx, NoFaults(), self._pre_state)
        if (reference.committed, reference.after_hash) != (
            execution.committed,
            execution.after_hash,
        ):
            # Observation would contradict the state actually produced (REPLAY_SPEC §10.3).
            raise InterventionUnsupported("observation_inconsistent_with_state")
        return reference.response

    def _after_tool(self, event: Event, entry: LedgerEntry) -> None:
        if self.fenced:
            return
        if event.seq != self._target:
            super()._after_tool(event, entry)
            return
        verify_original = not (
            self._request.intervention_type is EXE
            and self._request.reference_source is ReferenceSource.REFERENCE_TOOL
        )
        if verify_original:
            # The original execution was re-applied: it must match the recording exactly,
            # except the delivered value under OBSERVATION_REPLACEMENT.
            assert self._target_entry is not None
            recorded = self._target_entry
            if self._request.intervention_type is OBS:
                event = event.model_copy(update={"response_fp": recorded.event.response_fp})
            self._pending = recorded
            super()._after_tool(event, entry)
        self._fence()

    def finish(self) -> None:
        if not self.fenced:
            super().finish()  # target never reached: prefix diverged (TRUNCATED)


class _FencedPolicy:
    """Delegates to the live policy only after the fence; before it, any call is a bug."""

    def __init__(self, live: Policy[Any], holder: list[CounterfactualGateway[Any]]) -> None:
        self._live = live
        self._holder = holder
        self.prefix_calls = 0

    @property
    def policy_id(self) -> str:
        return self._live.policy_id

    @property
    def policy_version(self) -> str:
        return self._live.policy_version

    @property
    def source_hash(self) -> str:
        return self._live.source_hash

    @property
    def deterministic(self) -> bool:
        return self._live.deterministic

    def decide(self, task: Any, history: Sequence[Observation]) -> Decision:
        if not self._holder or not self._holder[0].fenced:
            self.prefix_calls += 1
            raise LiveCallAttempted("policy invoked before the intervention point")
        return self._live.decide(task, history)


# ---------------------------------------------------------------- driver
def intervene(
    original: RunRecord,
    ctx: ReplayContext,
    request: InterventionRequest,
    *,
    allow_privileged: bool = False,
) -> CounterfactualResult:
    """Execute one counterfactual replay (REPLAY_SPEC §5.3). Never invents an outcome."""
    header = original.header

    def result(
        status: CounterfactualStatus,
        reason: str | None = None,
        run: RunRecord | None = None,
        divergence: Divergence | None = None,
        accesses_after_fence: int = 0,
    ) -> CounterfactualResult:
        return CounterfactualResult(
            status=status,
            request=request,
            original_run_id=header.run_id,
            original_outcome=original.footer.outcome.outcome,
            reason=reason,
            run=run,
            divergence=divergence,
            cassette_accesses_after_fence=accesses_after_fence,
        )

    config = check_config(header, original.fault_plan, ctx)
    if not config.ok:
        return result(CounterfactualStatus.CONFIG_MISMATCH, "; ".join(config.mismatches))
    reason = precheck(original, request, ctx, allow_privileged=allow_privileged)
    if reason is not None:
        return result(CounterfactualStatus.UNSUPPORTED, reason)

    target = _target_entry(original, request.target_seq)
    assert target is not None
    agent = header.agent
    live = ctx.make_policy(agent.policy_id, agent.policy_version)
    assert live is not None
    decider = ctx.reference_decider(agent.policy_id, agent.policy_version)
    cassette = Cassette(original)
    holder: list[CounterfactualGateway[Any]] = []

    def factory(
        *, run_id: str, state: Any, tools: Mapping[str, ToolSpec[Any]], fault_hook: FaultHook
    ) -> BoundaryGateway[Any]:
        gateway: CounterfactualGateway[Any] = CounterfactualGateway(
            run_id=run_id,
            state=state,
            tools=tools,
            fault_hook=fault_hook,
            cassette=cassette,
            request=request,
            decider=decider,
        )
        holder.append(gateway)
        return gateway

    intervention = Intervention(
        target_seq=request.target_seq,
        target_logical_key=target.event.logical_key,
        boundary=target.event.boundary,
        intervention_type=request.intervention_type,
        reference_source=request.reference_source,
        is_placebo=request.is_placebo,
        replacement_fp=(
            target.event.response_fp
            if request.reference_source is ReferenceSource.ORIGINAL
            and request.intervention_type is OBS
            else None
        ),
        expected_semantics=request.expected_semantics or request.intervention_type.value,
    )
    try:
        run = run_episode(
            ctx.build_episode(header, original.fault_plan),
            _FencedPolicy(live, holder),
            mode=RunMode.REPLAY_INTERVENE,
            parent_run_id=header.run_id,
            gateway_factory=factory,
            intervention=intervention,
        )
    except InterventionUnsupported as exc:
        return result(CounterfactualStatus.UNSUPPORTED, exc.reason)
    gateway = holder[0]
    if run.footer.status is RunStatus.DIVERGED:
        return result(
            CounterfactualStatus.INVALID_COUNTERFACTUAL,
            "prefix_diverged",
            run=run,
            divergence=run.footer.divergence,
        )
    return result(
        CounterfactualStatus.COMPLETED,
        run=run,
        accesses_after_fence=cassette.accesses - gateway.accesses_at_fence,
    )


# ---------------------------------------------------------------- experiments
def _signature(record: RunRecord) -> tuple[Any, ...]:
    footer = record.footer
    clauses = tuple(c.clause_id for c in footer.outcome.violated_clauses)
    return footer.status, footer.outcome.outcome, clauses, footer.final_state_hash


@dataclass(frozen=True)
class ExperimentResult:
    """One reference intervention plus its same-type placebo (REPLAY_SPEC §14)."""

    target_seq: int
    target_logical_key: str
    boundary: Boundary
    intervention_type: InterventionType
    reference_source: ReferenceSource
    original_outcome: Outcome
    intervention: CounterfactualResult
    placebo: CounterfactualResult

    @property
    def placebo_valid(self) -> bool:
        if self.placebo.status is not CounterfactualStatus.COMPLETED or self.placebo.run is None:
            return False
        return self._original_signature == _signature(self.placebo.run)

    @property
    def repair_observed(self) -> bool:
        return (
            self.original_outcome is Outcome.FAIL
            and self.intervention.status is CounterfactualStatus.COMPLETED
            and self.intervention.outcome is Outcome.PASS
        )

    @property
    def interventional_repair(self) -> bool:
        return self.repair_observed and self.placebo_valid

    _original_signature: tuple[Any, ...] = ()


def run_experiment(
    original: RunRecord,
    ctx: ReplayContext,
    request: InterventionRequest,
    *,
    allow_privileged: bool = False,
) -> ExperimentResult:
    target = _target_entry(original, request.target_seq)
    main = intervene(original, ctx, request, allow_privileged=allow_privileged)
    placebo = intervene(original, ctx, request.placebo(), allow_privileged=allow_privileged)
    return ExperimentResult(
        target_seq=request.target_seq,
        target_logical_key=target.event.logical_key if target else "",
        boundary=target.event.boundary if target else Boundary.AGENT_STEP,
        intervention_type=request.intervention_type,
        reference_source=request.reference_source,
        original_outcome=original.footer.outcome.outcome,
        intervention=main,
        placebo=placebo,
        _original_signature=_signature(original),
    )


def default_request(original: RunRecord, seq: int) -> InterventionRequest | None:
    """The faithful default intervention for a step (PLAN §11.2): tools → EXECUTION with
    REFERENCE_TOOL; decisions → OBSERVATION with REFERENCE_POLICY."""
    target = _target_entry(original, seq)
    if target is None:
        return None
    if target.event.boundary is Boundary.TOOL:
        return InterventionRequest(seq, EXE, ReferenceSource.REFERENCE_TOOL, "clean execution")
    return InterventionRequest(seq, OBS, ReferenceSource.REFERENCE_POLICY, "reference decision")


# ---------------------------------------------------------------- reference probe
class ProbeOutcome(StrEnum):
    DEVIATES = "DEVIATES"
    CONSISTENT = "CONSISTENT"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ProbeResult:
    outcome: ProbeOutcome
    reason: str | None = None


class _ProbeDone(Exception):
    def __init__(self, result: ProbeResult) -> None:
        super().__init__(result.outcome.value)
        self.result = result


class _ProbeGateway[S: BaseModel](StrictReplayGateway[S]):
    def __init__(self, *, target: int, decider: ReferenceDecider | None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._target = target
        self._decider = decider

    def _produce_decision[T: BaseModel](
        self,
        ctx: DecisionContext,
        request_fp: str,
        policy: Policy[T],
        task: T,
        history: Sequence[Observation],
    ) -> tuple[Decision, Decision, list[FaultApplication]]:
        if ctx.seq != self._target:
            return super()._produce_decision(ctx, request_fp, policy, task, history)
        entry = self._cassette.expect(ctx.seq, Boundary.DECISION, "decide", request_fp)
        if self._decider is None:
            raise _ProbeDone(ProbeResult(ProbeOutcome.UNSUPPORTED, "no_trusted_reference"))
        reference = self._decider.reference_decision(task, history)
        deviates = fingerprint(reference) != entry.event.response_fp
        raise _ProbeDone(
            ProbeResult(ProbeOutcome.DEVIATES if deviates else ProbeOutcome.CONSISTENT)
        )

    def _before_tool(self, seq: int, name: str, request_fp: str) -> None:
        if seq != self._target:
            super()._before_tool(seq, name, request_fp)
            return
        entry = self._cassette.expect(seq, Boundary.TOOL, name, request_fp)
        recorded = entry.event
        assert recorded.state is not None and isinstance(recorded.request, dict)
        ctx = ToolContext(
            seq=seq,
            step_index=recorded.step_index,
            tool=name,
            args=recorded.request["args"],
            occurrence=0,
            attempt=recorded.attempt or 1,
        )
        reference = self.lifecycle(name, ctx.args, ctx, NoFaults(), self.state)
        same_response = fingerprint(reference.response) == recorded.response_fp
        same_state = (reference.committed, reference.after_hash) == (
            recorded.state.committed,
            recorded.state.after_hash,
        )
        outcome = ProbeOutcome.CONSISTENT if same_response and same_state else ProbeOutcome.DEVIATES
        raise _ProbeDone(ProbeResult(outcome))


def probe_reference(original: RunRecord, ctx: ReplayContext, seq: int) -> ProbeResult:
    """Compare the recorded value/transition at ``seq`` with its trusted reference.

    Replays the prefix strictly (one partial replay) and stops at the target.
    """
    target = _target_entry(original, seq)
    if target is None:
        return ProbeResult(ProbeOutcome.UNSUPPORTED, "target_not_boundary")
    config = check_config(original.header, original.fault_plan, ctx)
    if not config.ok:
        return ProbeResult(ProbeOutcome.UNSUPPORTED, "config_mismatch")
    agent = original.header.agent
    decider = ctx.reference_decider(agent.policy_id, agent.policy_version)
    cassette = Cassette(original)

    def factory(
        *, run_id: str, state: Any, tools: Mapping[str, ToolSpec[Any]], fault_hook: FaultHook
    ) -> BoundaryGateway[Any]:
        return _ProbeGateway(
            run_id=run_id,
            state=state,
            tools=tools,
            fault_hook=fault_hook,
            cassette=cassette,
            target=seq,
            decider=decider,
        )

    try:
        run = run_episode(
            ctx.build_episode(original.header, original.fault_plan),
            ReplayPolicyGuard(agent),
            mode=RunMode.REPLAY_STRICT,
            parent_run_id=original.header.run_id,
            gateway_factory=factory,
        )
    except _ProbeDone as done:
        return done.result
    if run.footer.status is RunStatus.DIVERGED:
        return ProbeResult(ProbeOutcome.UNSUPPORTED, "prefix_diverged")
    return ProbeResult(ProbeOutcome.UNSUPPORTED, "target_not_reached")
