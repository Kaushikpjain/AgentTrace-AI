"""Reference-policy interface (REPLAY_SPEC section 10.2, ``REFERENCE_POLICY``).

A reference policy supplies trusted replacement decisions for counterfactual
OBSERVATION_REPLACEMENT at decision boundaries. It is queried with the *recorded* prefix
history. Used from Week 3; defined now so the contract is fixed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agenttrace.env.support.scenario import TaskSpec
from agenttrace.policies.support_scripted import ScriptedSupportPolicy
from agenttrace.runtime.types import Decision, Observation


class ReferencePolicy(Protocol):
    @property
    def reference_id(self) -> str: ...

    def reference_decision(self, task: TaskSpec, history: Sequence[Observation]) -> Decision: ...


class GoldSupportReference:
    """The gold trajectory generator for support scenarios: the corrected ``v2`` policy."""

    def __init__(self) -> None:
        self._policy = ScriptedSupportPolicy("v2")

    @property
    def reference_id(self) -> str:
        return f"{self._policy.policy_id}:{self._policy.policy_version}:gold"

    def reference_decision(self, task: TaskSpec, history: Sequence[Observation]) -> Decision:
        return self._policy.decide(task, history)
