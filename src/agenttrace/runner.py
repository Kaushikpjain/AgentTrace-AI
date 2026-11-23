"""Composition root: wires the support environment, oracle, policies and fault plans into the
runtime and replay engine. The only module that knows all concrete pieces.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agenttrace.env.base import ToolSpec
from agenttrace.env.support.models import SupportState
from agenttrace.env.support.scenario import Scenario, TaskSpec, load_scenario
from agenttrace.env.support.snapshot import restore
from agenttrace.env.support.tools import SUPPORT_TOOLS_BY_NAME, support_manifest_hash
from agenttrace.evals.oracle import ORACLE_REF, evaluate
from agenttrace.faults.plan import PlanFaultHook, validate_plan
from agenttrace.policies.reference import GoldSupportReference
from agenttrace.policies.support_scripted import PolicyVersion, ScriptedSupportPolicy
from agenttrace.replay.exact import ReferenceDecider, ReplayContext
from agenttrace.runtime.faults import NoFaults
from agenttrace.runtime.loop import EpisodeSpec, run_episode
from agenttrace.runtime.types import Policy
from agenttrace.trace.schema import AgentRef, FaultPlan, RunHeader, RunRecord, ScenarioRef

POLICY_VERSIONS: tuple[PolicyVersion, ...] = ("v1", "v2")


def scenario_ref(scenario: Scenario) -> ScenarioRef:
    return ScenarioRef(
        id=scenario.scenario_id,
        version=scenario.version,
        initial_state_hash=scenario.initial_state_hash(),
    )


def episode_for(
    scenario: Scenario,
    *,
    fault_plan: FaultPlan | None = None,
    max_steps: int | None = None,
    tools: Mapping[str, ToolSpec[Any]] | None = None,
    tool_manifest_hash: str | None = None,
) -> EpisodeSpec[SupportState, TaskSpec]:
    """Build an episode with a FRESH state restored from the scenario snapshot (invariant I4).

    ``tools``/``tool_manifest_hash`` overrides exist for replay-divergence tests only.
    """
    expected = scenario.expected
    return EpisodeSpec(
        scenario=scenario_ref(scenario),
        initial_state=restore(scenario.initial_snapshot()),
        task=scenario.task,
        tools=tools if tools is not None else SUPPORT_TOOLS_BY_NAME,
        tool_manifest_hash=tool_manifest_hash or support_manifest_hash(),
        oracle=lambda state: evaluate(expected, state),
        oracle_ref=ORACLE_REF,
        max_steps=max_steps if max_steps is not None else scenario.max_steps,
        fault_hook=PlanFaultHook(fault_plan) if fault_plan is not None else NoFaults(),
        fault_plan=fault_plan,
    )


def make_policy(version: PolicyVersion) -> Policy[TaskSpec]:
    return ScriptedSupportPolicy(version)


def record_scenario(
    scenario: Scenario,
    *,
    policy_version: PolicyVersion = "v1",
    fault_plan: FaultPlan | None = None,
    max_steps: int | None = None,
) -> RunRecord:
    """Execute ``scenario`` in RECORD mode and return the (unsaved) recording."""
    spec = episode_for(scenario, fault_plan=fault_plan, max_steps=max_steps)
    return run_episode(spec, make_policy(policy_version))


def _current_scenario_ref(scenario_id: str) -> ScenarioRef | None:
    try:
        return scenario_ref(load_scenario(scenario_id))
    except KeyError:
        return None


def _current_agent_ref(policy_id: str, version: str) -> AgentRef | None:
    if policy_id != ScriptedSupportPolicy.policy_id or version not in POLICY_VERSIONS:
        return None
    policy = ScriptedSupportPolicy(version)
    return AgentRef(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        source_hash=policy.source_hash,
    )


def support_replay_context(
    *,
    tools: Mapping[str, ToolSpec[Any]] | None = None,
    tool_manifest_hash: str | None = None,
) -> ReplayContext:
    """ReplayContext for the support environment (overrides are for divergence tests only)."""
    manifest = tool_manifest_hash or support_manifest_hash()

    def build(header: RunHeader, plan: FaultPlan | None) -> EpisodeSpec[Any, Any]:
        return episode_for(
            load_scenario(header.scenario.id),
            fault_plan=plan,
            max_steps=header.max_steps,
            tools=tools,
            tool_manifest_hash=manifest,
        )

    return ReplayContext(
        current_scenario_ref=_current_scenario_ref,
        current_agent_ref=_current_agent_ref,
        tool_manifest_hash=manifest,
        oracle_ref=ORACLE_REF,
        validate_fault_plan=validate_plan,
        build_episode=build,
        make_policy=_make_policy,
        reference_decider=_reference_decider,
    )


def _make_policy(policy_id: str, version: str) -> Policy[Any] | None:
    if policy_id != ScriptedSupportPolicy.policy_id or version not in POLICY_VERSIONS:
        return None
    return ScriptedSupportPolicy(version)


def _reference_decider(policy_id: str, version: str) -> ReferenceDecider | None:
    if policy_id != ScriptedSupportPolicy.policy_id or version not in POLICY_VERSIONS:
        return None
    return GoldSupportReference(version)
