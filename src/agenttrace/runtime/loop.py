"""Minimal agent loop (RECORD mode, REPLAY_SPEC section 5.1). Environment-agnostic."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

import agenttrace
from agenttrace.env.base import ToolSpec
from agenttrace.runtime.faults import FaultHook, NoFaults
from agenttrace.runtime.gateway import BoundaryGateway
from agenttrace.runtime.types import Observation, Policy
from agenttrace.trace.ids import new_run_id, utc_now
from agenttrace.trace.integrity import compute_chain_root
from agenttrace.trace.schema import (
    SCHEMA_VERSION,
    AgentRef,
    Boundary,
    Integrity,
    OracleRef,
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


def run_episode[S: BaseModel, T: BaseModel](
    spec: EpisodeSpec[S, T], policy: Policy[T], *, mode: RunMode = RunMode.RECORD
) -> RunRecord:
    """Execute the agent loop through the gateway and assemble a validated RunRecord."""
    if mode is not RunMode.RECORD:
        raise NotImplementedError(f"mode {mode} is implemented in a later milestone")
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
        config_fingerprint=compute_config_fingerprint(**fingerprint_fields),
        started_at=started_at,
        agenttrace_version=agenttrace.__version__,
        **fingerprint_fields,
    )

    gateway: BoundaryGateway[S] = BoundaryGateway(
        run_id=run_id, state=spec.initial_state, tools=spec.tools, fault_hook=spec.fault_hook
    )
    history: list[Observation] = []
    status = RunStatus.MAX_STEPS
    steps = 0
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

    outcome = spec.oracle(gateway.state)
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
        ended_at=utc_now(),
        wall_ms=int((time.perf_counter() - t0) * 1000),
        integrity=Integrity(
            event_count=len(events),
            ledger_count=len(ledger),
            chain_root=compute_chain_root(events, ledger),
        ),
    )
    return RunRecord(header=header, events=events, ledger=ledger, footer=footer)
