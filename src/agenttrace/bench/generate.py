"""AgentTrace-Synth v0 candidate generator (PLAN_v0.2.1 section 12).

Deterministic enumeration (no sampling): every template x applicable operator x site, derived
from the template's clean recording. ``SEED`` is recorded in the manifest for completeness; the
enumeration does not depend on it. Candidates are *not* benchmark instances until validated
(``agenttrace.bench.validate``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from agenttrace.env.support.scenario import list_scenario_ids, load_scenario
from agenttrace.policies.support_scripted import PolicyVersion
from agenttrace.runner import record_scenario
from agenttrace.trace.canonical import decimal_to_str, to_json_value
from agenttrace.trace.schema import (
    Boundary,
    FaultPlan,
    FaultSpec,
    FaultStage,
    FaultTrigger,
    RunRecord,
)

BENCHMARK_VERSION = "synth_v0"
GENERATOR_VERSION = "1"
SEED = 0
POLICY_VERSION: PolicyVersion = "v1"  # the agent under test
ARCHIVED_DOC = "POL-REFUND-2019"

EXPECTED_CATEGORY = {
    "WRONG_TOOL": "TOOL_SELECTION",
    "WRONG_ARGUMENT": "TOOL_ARGUMENT",
    "CORRUPT_OUTPUT": "TOOL_OUTPUT",
    "WRONG_RETRIEVAL": "RETRIEVAL",
    "LOST_ACK": "STATE",
}


@dataclass(frozen=True)
class Candidate:
    instance_id: str
    scenario_id: str
    split: str
    kind: str  # CLEAN | SINGLE | DECOY_ONLY | DECOY_PLUS | MULTI
    fault_plan: FaultPlan | None
    causal_fault_ids: tuple[str, ...] = ()
    decoy_fault_ids: tuple[str, ...] = ()


def _tool(
    fault_id: str, operator: str, stage: FaultStage, tool: str, params: dict[str, Any]
) -> FaultSpec:
    return FaultSpec(
        fault_id=fault_id,
        operator=operator,
        stage=stage,
        trigger=FaultTrigger(boundary=Boundary.TOOL, name=tool, occurrence=1),
        params=params,
    )


def _decision(fault_id: str, operator: str, occurrence: int, params: dict[str, Any]) -> FaultSpec:
    return FaultSpec(
        fault_id=fault_id,
        operator=operator,
        stage=FaultStage.DECISION,
        trigger=FaultTrigger(boundary=Boundary.DECISION, occurrence=occurrence),
        params=params,
    )


def _decision_occurrence_for(clean: RunRecord, tool: str) -> int | None:
    """1-based decision occurrence of the clean decision that calls ``tool`` first."""
    decisions = [e for e in clean.events if e.boundary is Boundary.DECISION]
    for index, event in enumerate(decisions, start=1):
        if isinstance(event.response, dict) and event.response.get("tool") == tool:
            return index
    return None


def _clean_tool_data(clean: RunRecord, tool: str) -> dict[str, Any]:
    event = next(e for e in clean.events if e.boundary is Boundary.TOOL and e.name == tool)
    response = event.response if isinstance(event.response, dict) else {}
    data = response.get("data")
    return data if isinstance(data, dict) else {}


def candidates_for(scenario_id: str) -> list[Candidate]:
    scenario = load_scenario(scenario_id)
    task = scenario.task
    clean = record_scenario(scenario, policy_version=POLICY_VERSION)
    order = _clean_tool_data(clean, "get_order")
    total = Decimal(str(order["total"]))
    refunding = _decision_occurrence_for(clean, "issue_refund")
    action = refunding or _decision_occurrence_for(clean, "close_ticket")
    get_order_decision = _decision_occurrence_for(clean, "get_order")
    assert action is not None and get_order_decision is not None
    archived = to_json_value(scenario.initial_state.policy_docs[ARCHIVED_DOC])
    sid = scenario_id
    out: list[Candidate] = []

    def single(name: str, spec: FaultSpec) -> None:
        out.append(
            Candidate(
                instance_id=f"{sid}-{name}",
                scenario_id=sid,
                split=scenario.split,
                kind="SINGLE",
                fault_plan=FaultPlan(plan_id=f"{sid}-{name}", faults=(spec,)),
                causal_fault_ids=(spec.fault_id,),
            )
        )

    out.append(Candidate(f"{sid}-clean", sid, scenario.split, "CLEAN", None))
    # F1 wrong tool at the action decision.
    if refunding:
        f1_args: dict[str, Any] = {
            "ticket_id": task.ticket_id,
            "resolution": "DENIED",
            "note": "wrong tool",
        }
        single(
            "F1", _decision("f1", "WRONG_TOOL", action, {"tool": "close_ticket", "args": f1_args})
        )
    else:
        f1_args = {"order_id": task.order_id, "amount": decimal_to_str(total)}
        single(
            "F1", _decision("f1", "WRONG_TOOL", action, {"tool": "issue_refund", "args": f1_args})
        )
    # F2 wrong / invalid arguments.
    single(
        "F2-order",
        _decision(
            "f2",
            "WRONG_ARGUMENT",
            get_order_decision,
            {"tool": "get_order", "arg": "order_id", "mode": "replace", "value": "O-UNKNOWN"},
        ),
    )
    if refunding:
        single(
            "F2-amount",
            _decision(
                "f2",
                "WRONG_ARGUMENT",
                refunding,
                {"tool": "issue_refund", "arg": "amount", "mode": "drop"},
            ),
        )
    siblings = sorted(o for o in scenario.initial_state.orders if o != task.order_id)
    if siblings:
        single(
            "F2-sibling",
            _decision(
                "f2",
                "WRONG_ARGUMENT",
                get_order_decision,
                {"tool": "get_order", "arg": "order_id", "mode": "replace", "value": siblings[0]},
            ),
        )
    # F3 corrupted output (delayed effect).
    single(
        "F3",
        _tool(
            "f3",
            "CORRUPT_OUTPUT",
            FaultStage.POST_EXECUTION,
            "get_order",
            {"path": ["data", "total"], "value": decimal_to_str(total * 10)},
        ),
    )
    # F4 incorrect retrieval (delayed effect).
    f4 = _tool(
        "f4", "WRONG_RETRIEVAL", FaultStage.POST_EXECUTION, "search_policy", {"data": archived}
    )
    single("F4", f4)
    # F5 lost acknowledgement (state / retry / idempotency).
    if refunding:
        single("F5", _tool("f5", "LOST_ACK", FaultStage.POST_EXECUTION, "issue_refund", {}))
    # D1 decoy: a harmless redundant read replacing the get_order decision.
    decoy = _decision(
        "d1",
        "DECOY_READ",
        get_order_decision,
        {"tool": "get_customer", "args": {"customer_id": task.customer_id}},
    )
    out.append(
        Candidate(
            f"{sid}-D1",
            sid,
            scenario.split,
            "DECOY_ONLY",
            FaultPlan(plan_id=f"{sid}-D1", faults=(decoy,)),
            decoy_fault_ids=("d1",),
        )
    )
    out.append(
        Candidate(
            f"{sid}-D1+F4",
            sid,
            scenario.split,
            "DECOY_PLUS",
            FaultPlan(plan_id=f"{sid}-D1+F4", faults=(decoy, f4)),
            causal_fault_ids=("f4",),
            decoy_fault_ids=("d1",),
        )
    )
    return out


def multi_fault_candidates() -> list[Candidate]:
    """Two-fault cases, reported separately (single-step limitation study)."""
    out: list[Candidate] = []
    for sid, extra in (("T6", "sibling"), ("T8", "corrupt")):
        scenario = load_scenario(sid)
        clean = record_scenario(scenario, policy_version=POLICY_VERSION)
        archived = to_json_value(scenario.initial_state.policy_docs[ARCHIVED_DOC])
        f4 = _tool(
            "f4", "WRONG_RETRIEVAL", FaultStage.POST_EXECUTION, "search_policy", {"data": archived}
        )
        if extra == "sibling":
            occurrence = _decision_occurrence_for(clean, "get_order")
            assert occurrence is not None
            sibling = sorted(
                o for o in scenario.initial_state.orders if o != scenario.task.order_id
            )[0]
            second = _decision(
                "f2",
                "WRONG_ARGUMENT",
                occurrence,
                {"tool": "get_order", "arg": "order_id", "mode": "replace", "value": sibling},
            )
        else:
            total = Decimal(str(_clean_tool_data(clean, "get_order")["total"]))
            second = _tool(
                "f3",
                "CORRUPT_OUTPUT",
                FaultStage.POST_EXECUTION,
                "get_order",
                {"path": ["data", "total"], "value": decimal_to_str(total * 10)},
            )
        name = f"{sid}-MULTI-F4+{second.fault_id.upper()}"
        out.append(
            Candidate(
                name,
                sid,
                scenario.split,
                "MULTI",
                FaultPlan(plan_id=name, faults=(second, f4)),
                causal_fault_ids=(second.fault_id, "f4"),
            )
        )
    return out


def generate_candidates() -> list[Candidate]:
    candidates = [c for sid in list_scenario_ids() for c in candidates_for(sid)]
    return candidates + multi_fault_candidates()
