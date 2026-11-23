"""REPLAY_STRICT: exact replay with state re-application and fail-closed verification.

Authoritative semantics: docs/REPLAY_SPEC.md sections 5.2, 6, 7, 8, 11, 12.
Environment-agnostic: the concrete environment is supplied through a ReplayContext.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from agenttrace.env.base import ToolSpec
from agenttrace.replay.cassette import Cassette, CassetteEntry
from agenttrace.replay.fidelity import FidelityReport, compute_fidelity, outcome_key
from agenttrace.runtime.faults import DecisionContext, FaultHook
from agenttrace.runtime.gateway import BoundaryGateway, DivergenceDetected
from agenttrace.runtime.loop import EpisodeSpec, run_episode
from agenttrace.runtime.types import Decision, Observation, Policy
from agenttrace.trace.fingerprint import fingerprint
from agenttrace.trace.schema import (
    AgentRef,
    Boundary,
    Divergence,
    DivergenceKind,
    Event,
    FaultApplication,
    FaultPlan,
    LedgerEntry,
    OracleRef,
    RunHeader,
    RunMode,
    RunRecord,
    RunStatus,
    ScenarioRef,
)
from agenttrace.trace.store import RunNotFoundError, TraceStore, TraceStoreError


class ReplayVerdict(StrEnum):
    VERIFIED = "VERIFIED"
    DIVERGED = "DIVERGED"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"


class LiveCallAttempted(RuntimeError):
    """The policy was invoked during strict replay (must never happen)."""


@dataclass(frozen=True)
class ReplayContext:
    """What strict replay needs from a concrete environment (built by the composition root)."""

    current_scenario_ref: Callable[[str], ScenarioRef | None]
    current_agent_ref: Callable[[str, str], AgentRef | None]
    tool_manifest_hash: str
    oracle_ref: OracleRef
    validate_fault_plan: Callable[[FaultPlan], None]  # raises ValueError if not replayable
    # (header, fault_plan) -> episode with a FRESH initial state and header.max_steps
    build_episode: Callable[[RunHeader, FaultPlan | None], EpisodeSpec[Any, Any]]


@dataclass(frozen=True)
class ConfigCheck:
    mismatches: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches


@dataclass(frozen=True)
class ReplayReport:
    verdict: ReplayVerdict
    original_run_id: str
    config: ConfigCheck
    replay: RunRecord | None = None
    divergence: Divergence | None = None
    fidelity: FidelityReport | None = None
    integrity_error: str | None = None
    policy_calls: int = 0
    cassette_entries: int = 0
    cassette_consumed: int = 0


# ---------------------------------------------------------------- configuration check
def check_config(
    header: RunHeader,
    fault_plan: FaultPlan | None,
    ctx: ReplayContext,
    *,
    policy_version: str | None = None,
) -> ConfigCheck:
    """Compare every config-fingerprint component with the current code (REPLAY_SPEC §8)."""
    problems: list[str] = []
    scenario = ctx.current_scenario_ref(header.scenario.id)
    if scenario is None:
        problems.append(f"scenario: {header.scenario.id!r} is unknown")
    elif scenario != header.scenario:
        problems.append("scenario: version or initial state differs from the recording")
    version = policy_version or header.agent.policy_version
    agent = ctx.current_agent_ref(header.agent.policy_id, version)
    if agent is None:
        problems.append(f"agent: policy {header.agent.policy_id}:{version} is unknown")
    elif agent != header.agent:
        if agent.policy_version != header.agent.policy_version:
            problems.append(
                f"agent: policy version {agent.policy_version} != recorded "
                f"{header.agent.policy_version}"
            )
        if agent.source_hash != header.agent.source_hash:
            problems.append("agent: policy source code changed since the recording")
    if ctx.tool_manifest_hash != header.tool_manifest_hash:
        problems.append("tools: tool manifest (names, schemas or source) changed")
    if ctx.oracle_ref != header.oracle:
        problems.append(f"oracle: {ctx.oracle_ref.id}:{ctx.oracle_ref.version} != recorded")
    if header.fault_plan_hash is not None:
        if fault_plan is None:
            problems.append("fault_plan: recorded fault plan is unavailable")
        else:
            try:
                ctx.validate_fault_plan(fault_plan)
            except ValueError as exc:
                problems.append(f"fault_plan: not replayable ({exc})")
    return ConfigCheck(tuple(problems))


# ---------------------------------------------------------------- guard policy
class ReplayPolicyGuard:
    """Stands in for the policy during strict replay; any decide() call is a bug."""

    def __init__(self, agent: AgentRef) -> None:
        self._agent = agent
        self.calls = 0

    @property
    def policy_id(self) -> str:
        return self._agent.policy_id

    @property
    def policy_version(self) -> str:
        return self._agent.policy_version

    @property
    def source_hash(self) -> str:
        return self._agent.source_hash

    @property
    def deterministic(self) -> bool:
        return True

    def decide(self, task: Any, history: Sequence[Observation]) -> Decision:
        self.calls += 1
        raise LiveCallAttempted("the policy must not be invoked during strict replay")


# ---------------------------------------------------------------- replaying gateway
class StrictReplayGateway[S: BaseModel](BoundaryGateway[S]):
    """Serves decisions from the cassette; re-executes tools and verifies every fact."""

    def __init__(
        self,
        *,
        run_id: str,
        state: S,
        tools: Mapping[str, ToolSpec[Any]],
        fault_hook: FaultHook,
        cassette: Cassette,
    ) -> None:
        super().__init__(run_id=run_id, state=state, tools=tools, fault_hook=fault_hook)
        self._cassette = cassette
        self._pending: CassetteEntry | None = None

    def _produce_decision[T: BaseModel](
        self,
        ctx: DecisionContext,
        request_fp: str,
        policy: Policy[T],
        task: T,
        history: Sequence[Observation],
    ) -> tuple[Decision, Decision, list[FaultApplication]]:
        entry = self._cassette.expect(ctx.seq, Boundary.DECISION, "decide", request_fp)
        raw = Decision.model_validate(entry.ledger.raw_output)
        delivered = Decision.model_validate(entry.event.response)
        return raw, delivered, list(entry.ledger.fault_applications)

    def _before_tool(self, seq: int, name: str, request_fp: str) -> None:
        self._pending = self._cassette.expect(seq, Boundary.TOOL, name, request_fp)

    def _after_tool(self, event: Event, entry: LedgerEntry) -> None:
        recorded = self._pending
        assert recorded is not None
        self._pending = None
        exp_e, exp_l = recorded.event, recorded.ledger

        def diverge(kind: DivergenceKind, detail: str, expected: Any, actual: Any) -> None:
            raise DivergenceDetected(
                Divergence(
                    seq=event.seq,
                    kind=kind,
                    expected_fp=fingerprint(expected),
                    actual_fp=fingerprint(actual),
                    detail=detail,
                )
            )

        exp_raw = (exp_l.executed, exp_l.raw_output_fp, exp_l.fault_applications)
        act_raw = (entry.executed, entry.raw_output_fp, entry.fault_applications)
        if exp_raw != act_raw:
            what = "executed flag" if exp_l.executed != entry.executed else "raw result"
            if exp_l.executed == entry.executed and exp_l.raw_output_fp == entry.raw_output_fp:
                what = "fault applications"
            diverge(
                DivergenceKind.RAW_RESULT,
                f"{event.name}: {what} differs from the recording",
                [exp_l.executed, exp_l.raw_output_fp, list(exp_l.fault_applications)],
                [entry.executed, entry.raw_output_fp, list(entry.fault_applications)],
            )
        assert exp_e.state is not None and event.state is not None
        exp_state = (exp_e.state.committed, exp_e.state.before_hash, exp_e.state.after_hash)
        act_state = (event.state.committed, event.state.before_hash, event.state.after_hash)
        if exp_state != act_state:
            diverge(
                DivergenceKind.STATE,
                f"{event.name}: state transition differs (committed/before/after hash)",
                list(exp_state),
                list(act_state),
            )
        if exp_e.response_fp != event.response_fp:
            diverge(
                DivergenceKind.RESPONSE,
                f"{event.name}: delivered response differs from the recording",
                exp_e.response_fp,
                event.response_fp,
            )

    def finish(self) -> None:
        if self._cassette.remaining:
            seq = self._cassette.peek_seq()
            raise DivergenceDetected(
                Divergence(
                    seq=seq if seq is not None else 0,
                    kind=DivergenceKind.TRUNCATED,
                    detail=f"run ended with {self._cassette.remaining} unconsumed cassette entries",
                )
            )


# ---------------------------------------------------------------- driver
def replay_strict(
    original: RunRecord, ctx: ReplayContext, *, policy_version: str | None = None
) -> ReplayReport:
    """Replay a validated recording exactly (REPLAY_SPEC §5.2). Never calls the policy."""
    header = original.header
    config = check_config(header, original.fault_plan, ctx, policy_version=policy_version)
    if not config.ok:
        return ReplayReport(
            verdict=ReplayVerdict.CONFIG_MISMATCH,
            original_run_id=header.run_id,
            config=config,
        )

    spec = ctx.build_episode(header, original.fault_plan)
    cassette = Cassette(original)
    guard = ReplayPolicyGuard(header.agent)

    def factory(
        *, run_id: str, state: Any, tools: Mapping[str, ToolSpec[Any]], fault_hook: FaultHook
    ) -> BoundaryGateway[Any]:
        return StrictReplayGateway(
            run_id=run_id, state=state, tools=tools, fault_hook=fault_hook, cassette=cassette
        )

    replay = run_episode(
        spec,
        guard,
        mode=RunMode.REPLAY_STRICT,
        parent_run_id=header.run_id,
        gateway_factory=factory,
    )

    divergence = replay.footer.divergence
    if divergence is None:
        last_seq = replay.events[-1].seq if replay.events else 0
        if replay.footer.final_state_hash != original.footer.final_state_hash:
            divergence = Divergence(
                seq=last_seq,
                kind=DivergenceKind.STATE,
                expected_fp=original.footer.final_state_hash,
                actual_fp=replay.footer.final_state_hash,
                detail="final state differs from the recording",
            )
        elif outcome_key(replay) != outcome_key(original):
            divergence = Divergence(
                seq=last_seq,
                kind=DivergenceKind.OUTCOME,
                expected_fp=fingerprint(list(outcome_key(original))),
                actual_fp=fingerprint(list(outcome_key(replay))),
                detail="run status, oracle outcome or violated clauses differ",
            )
        if divergence is not None:
            footer = replay.footer.model_copy(
                update={"status": RunStatus.DIVERGED, "divergence": divergence}
            )
            replay = replay.model_copy(update={"footer": footer})

    return ReplayReport(
        verdict=ReplayVerdict.VERIFIED if divergence is None else ReplayVerdict.DIVERGED,
        original_run_id=header.run_id,
        config=config,
        replay=replay,
        divergence=divergence,
        fidelity=compute_fidelity(original, replay),
        policy_calls=guard.calls,
        cassette_entries=len(cassette),
        cassette_consumed=cassette.position,
    )


def replay_run(
    store: TraceStore, run_id: str, ctx: ReplayContext, *, policy_version: str | None = None
) -> ReplayReport:
    """Load (with full integrity validation) and strictly replay a stored run.

    RunNotFoundError propagates; any other store error yields INTEGRITY_ERROR.
    """
    try:
        original = store.load_record(run_id)
    except RunNotFoundError:
        raise
    except TraceStoreError as exc:
        return ReplayReport(
            verdict=ReplayVerdict.INTEGRITY_ERROR,
            original_run_id=run_id,
            config=ConfigCheck(()),
            integrity_error=f"{type(exc).__name__}: {exc}",
        )
    return replay_strict(original, ctx, policy_version=policy_version)
