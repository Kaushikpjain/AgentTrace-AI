"""Composition root: wires the support environment, oracle and policies into the runtime."""

from __future__ import annotations

from agenttrace.env.support.models import SupportState
from agenttrace.env.support.scenario import Scenario, TaskSpec
from agenttrace.env.support.snapshot import restore
from agenttrace.env.support.tools import SUPPORT_TOOLS_BY_NAME, support_manifest_hash
from agenttrace.evals.oracle import ORACLE_REF, evaluate
from agenttrace.policies.support_scripted import PolicyVersion, ScriptedSupportPolicy
from agenttrace.runtime.faults import FaultHook, NoFaults
from agenttrace.runtime.loop import EpisodeSpec, run_episode
from agenttrace.runtime.types import Policy
from agenttrace.trace.schema import RunRecord, ScenarioRef


def episode_for(
    scenario: Scenario, *, fault_hook: FaultHook | None = None, max_steps: int | None = None
) -> EpisodeSpec[SupportState, TaskSpec]:
    """Build an episode with a FRESH state restored from the scenario snapshot (invariant I4)."""
    expected = scenario.expected
    return EpisodeSpec(
        scenario=ScenarioRef(
            id=scenario.scenario_id,
            version=scenario.version,
            initial_state_hash=scenario.initial_state_hash(),
        ),
        initial_state=restore(scenario.initial_snapshot()),
        task=scenario.task,
        tools=SUPPORT_TOOLS_BY_NAME,
        tool_manifest_hash=support_manifest_hash(),
        oracle=lambda state: evaluate(expected, state),
        oracle_ref=ORACLE_REF,
        max_steps=max_steps if max_steps is not None else scenario.max_steps,
        fault_hook=fault_hook if fault_hook is not None else NoFaults(),
    )


def make_policy(version: PolicyVersion) -> Policy[TaskSpec]:
    return ScriptedSupportPolicy(version)


def record_scenario(
    scenario: Scenario,
    *,
    policy_version: PolicyVersion = "v1",
    fault_hook: FaultHook | None = None,
    max_steps: int | None = None,
) -> RunRecord:
    """Execute ``scenario`` in RECORD mode and return the (unsaved) recording."""
    spec = episode_for(scenario, fault_hook=fault_hook, max_steps=max_steps)
    return run_episode(spec, make_policy(policy_version))
