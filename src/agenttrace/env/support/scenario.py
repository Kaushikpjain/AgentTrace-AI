"""Declarative, versioned scenario templates (package data, ADR-011)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agenttrace.env.support.models import Issue, Money, Resolution, SupportState
from agenttrace.env.support.snapshot import snapshot, state_hash


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskSpec(_Frozen):
    """What the agent is asked to resolve (the ticket as seen by the agent)."""

    ticket_id: str
    customer_id: str
    order_id: str
    issue: Issue
    sku: str | None = None


class ExpectedRefund(_Frozen):
    order_id: str
    amount: Money


class ExpectedTicket(_Frozen):
    ticket_id: str
    status: Literal["open", "closed"]
    resolution: Resolution | None


class ExpectedOutcome(_Frozen):
    """Oracle specification: the full expected final refund set and ticket state."""

    refunds: tuple[ExpectedRefund, ...]
    ticket: ExpectedTicket


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    version: str
    title: str
    description: str
    split: Literal["dev", "test"]
    scope: Literal["committed", "stretch"]
    max_steps: int = Field(default=12, ge=1, le=100)
    task: TaskSpec
    initial_state: SupportState
    expected: ExpectedOutcome

    def initial_snapshot(self) -> bytes:
        return snapshot(self.initial_state)

    def initial_state_hash(self) -> str:
        return state_hash(self.initial_state)


_PACKAGE = "agenttrace.env.support.scenarios"


@cache
def _load_raw(scenario_id: str) -> bytes:
    path = resources.files(_PACKAGE).joinpath(f"{scenario_id}.json")
    if not path.is_file():
        raise KeyError(f"unknown scenario {scenario_id!r}")
    return path.read_bytes()


def list_scenario_ids() -> list[str]:
    files = resources.files(_PACKAGE).iterdir()
    return sorted(f.name.removesuffix(".json") for f in files if f.name.endswith(".json"))


def load_scenario(scenario_id: str) -> Scenario:
    """Return a fresh Scenario object (callers can never mutate a shared instance)."""
    scenario = Scenario.model_validate(json.loads(_load_raw(scenario_id)))
    if scenario.scenario_id != scenario_id:
        raise ValueError(f"file {scenario_id}.json declares id {scenario.scenario_id!r}")
    return scenario
