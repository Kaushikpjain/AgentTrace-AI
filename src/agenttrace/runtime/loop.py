"""Minimal agent loop (RECORD mode, REPLAY_SPEC section 5.1). Environment-agnostic."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

import agenttrace
from agenttrace.env.base import ToolSpec
from agenttrace.runtime.faults import FaultHook, NoFaults
from agenttrace.runtime.gateway import BoundaryGateway, DivergenceDetected
from agenttrace.runtime.types import Observation, Policy
from agenttrace.trace.ids import new_run_id, utc_now
from agenttrace.trace.integrity import compute_chain_root
from agenttrace.trace.schema import (
    SCHEMA_VERSION,
    AgentRef,
    Boundary,
    Divergence,
    FaultPlan,
    Integrity,
    OracleRef,
    Outcome,
    OutcomeRecord,
    RunFooter,
    RunHeader,
    RunMode,
    RunRecord,
    RunStatus,
    ScenarioRef,
    Totals,
    compute_config_fingerprint,
)


@dataclass(frozen=True)
class EpisodeSpec[S: BaseModel, T: BaseModel]:
    """Everything needed to execute one run, independent of any concrete environment."""

    scenario: ScenarioRef
    initial_state: S  # must be a fresh object owned by this episode
    task: T
    tools: Mapping[str, ToolSpec[Any]]
    tool_manifest_hash: str
    oracle: Callable[[S], OutcomeRecord]
    oracle_ref: OracleRef
    max_steps: int
    fault_hook: FaultHook = field(default_factory=NoFaults)
    fault_plan: FaultPlan | None = None  # serializable plan behind fault_hook (if any)


class GatewayFactory[S: BaseModel](Protocol):
    def __call__(
        self, *, run_id: str, state: S, tools: Mapping[str, ToolSpec[Any]], fault_hook: FaultHook
    ) -> BoundaryGateway[S]: ...


_SUPPORTED_MODES = (RunMode.RECORD, RunMode.REPLAY_STRICT)


def run_episode[S: BaseModel, T: BaseModel](
    spec: EpisodeSpec[S, T],
    policy: Policy[T],
    *,
    mode: RunMode = RunMode.RECORD,
    parent_run_id: str | None = None,
    gateway_factory: GatewayFactory[S] | None = None,
) -> RunRecord:
    """Execute the agent loop through a gateway and assemble a validated RunRecord.

    RECORD uses the plain BoundaryGateway. Replay modes pass a ``gateway_factory`` whose
    gateway raises DivergenceDetected at the first mismatch; the run then ends with
    status DIVERGED and outcome NOT_EVALUATED (fail closed, REPLAY_SPEC section 5.2).
    """
    if mode not in _SUPPORTED_MODES:
        raise NotImplementedError(f"mode {mode} is implemented in a later milestone")
    if mode is not RunMode.RECORD and gateway_factory is None:
        raise ValueError(f"mode {mode} requires a replaying gateway factory")
    run_id = new_run_id()
    started_at = utc_now()
    t0 = time.perf_counter()
    agent = AgentRef(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        source_hash=policy.source_hash,
    )
    fingerprint_fields: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scenario": spec.scenario,
        "agent": agent,
        "tool_manifest_hash": spec.tool_manifest_hash,
        "fault_plan_hash": spec.fault_hook.fault_plan_hash,
        "oracle": spec.oracle_ref,
        "max_steps": spec.max_steps,
    }
    header = RunHeader(
        run_id=run_id,
        mode=mode,
        parent_run_id=parent_run_id,
        config_fingerprint=compute_config_fingerprint(**fingerprint_fields),
        started_at=started_at,
        agenttrace_version=agenttrace.__version__,
        **fingerprint_fields,
    )

    factory: GatewayFactory[S] = gateway_factory or BoundaryGateway
    gateway = factory(
        run_id=run_id, state=spec.initial_state, tools=spec.tools, fault_hook=spec.fault_hook
    )
    history: list[Observation] = []
    status = RunStatus.MAX_STEPS
    divergence: Divergence | None = None
    steps = 0
    try:
        for step_index in range(spec.max_steps):
            steps += 1
            span = gateway.open_step(step_index)
            decision = gateway.decide(
                policy, spec.task, tuple(history), step_index=step_index, parent_span_id=span
            )
            if decision.kind == "final":
                status = RunStatus.COMPLETED
                break
            seq = len(gateway.events)
            response = gateway.call_tool(decision, step_index=step_index, parent_span_id=span)
            assert decision.tool is not None
            history.append(
                Observation(seq=seq, tool=decision.tool, args=decision.args, response=response)
            )
        gateway.finish()
    except DivergenceDetected as signal:
        status = RunStatus.DIVERGED
        divergence = signal.divergence

    outcome = (
        spec.oracle(gateway.state)
        if divergence is None
        else OutcomeRecord(outcome=Outcome.NOT_EVALUATED)
    )
    events, ledger = gateway.events, gateway.ledger
    footer = RunFooter(
        status=status,
        outcome=outcome,
        final_state_hash=gateway.state_hash(),
        totals=Totals(
            events=len(events),
            decisions=sum(e.boundary is Boundary.DECISION for e in events),
            tool_calls=sum(e.boundary is Boundary.TOOL for e in events),
            steps=steps,
        ),
        divergence=divergence,
        ended_at=utc_now(),
        wall_ms=int((time.perf_counter() - t0) * 1000),
        integrity=Integrity(
            event_count=len(events),
            ledger_count=len(ledger),
            chain_root=compute_chain_root(header, events, ledger),
        ),
    )
    return RunRecord(
        header=header, events=events, ledger=ledger, footer=footer, fault_plan=spec.fault_plan
    )
