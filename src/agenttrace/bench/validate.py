"""Benchmark validator: turns candidates into validated instances with privileged labels.

PRIVILEGED module: reads ledgers and uses INJECTION_CLEAN_VALUE. Localizers never import it.

Per candidate:
1. The clean template run must PASS (otherwise the template is a bug).
2. The faulty run is recorded; every declared fault must actually fire (ledger fault
   applications); strict replay of the recording must be VERIFIED.
3. Label: CLEAN (no faults), DECOY_ONLY (decoy alone; must PASS, else rejected),
   CAUSAL (FAIL) or MASKED (PASS).
4. CAUSAL single-site instances are confirmed by an OBSERVATION_REPLACEMENT with the
   injection's clean value at the injection site (must repair); otherwise `confirmed=false`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agenttrace.bench.generate import EXPECTED_CATEGORY, POLICY_VERSION, Candidate
from agenttrace.env.support.scenario import load_scenario
from agenttrace.localize.observe import symptom_seq, tool_index_at_or_after
from agenttrace.replay.counterfactual import OBS, InterventionRequest, intervene
from agenttrace.replay.exact import ReplayContext, ReplayVerdict, replay_strict
from agenttrace.runner import record_scenario
from agenttrace.trace.schema import Outcome, ReferenceSource, RunRecord


@dataclass(frozen=True)
class Validated:
    instance: dict[str, Any]
    label: dict[str, Any]


@dataclass(frozen=True)
class Rejected:
    instance_id: str
    reason: str


def _sites(record: RunRecord, fault_ids: tuple[str, ...]) -> dict[str, list[int]]:
    sites: dict[str, list[int]] = {f: [] for f in fault_ids}
    for entry in record.ledger:
        for application in entry.fault_applications:
            if application.fault_id in sites:
                sites[application.fault_id].append(entry.seq)
    return sites


def record_candidate(candidate: Candidate) -> RunRecord:
    return record_scenario(
        load_scenario(candidate.scenario_id),
        policy_version=POLICY_VERSION,
        fault_plan=candidate.fault_plan,
    )


def validate_candidate(candidate: Candidate, ctx: ReplayContext) -> Validated | Rejected:
    clean = record_scenario(load_scenario(candidate.scenario_id), policy_version=POLICY_VERSION)
    if clean.footer.outcome.outcome is not Outcome.PASS:
        return Rejected(candidate.instance_id, "clean template run does not pass")
    record = clean if candidate.fault_plan is None else record_candidate(candidate)
    replay = replay_strict(record, ctx)
    if replay.verdict is not ReplayVerdict.VERIFIED:
        return Rejected(candidate.instance_id, f"strict replay {replay.verdict.value}")

    all_ids = candidate.causal_fault_ids + candidate.decoy_fault_ids
    sites = _sites(record, all_ids)
    silent = [f for f, seqs in sites.items() if not seqs]
    if silent:
        return Rejected(candidate.instance_id, f"fault(s) never fired: {', '.join(silent)}")
    multi_fired = [f for f, seqs in sites.items() if len(seqs) > 1]
    if multi_fired:
        return Rejected(candidate.instance_id, f"fault(s) fired more than once: {multi_fired}")

    outcome = record.footer.outcome.outcome
    trace = record.observable()
    symptom = symptom_seq(trace)
    operators = (
        {s.fault_id: s.operator for s in candidate.fault_plan.faults}
        if candidate.fault_plan
        else {}
    )
    injection_sites = [sites[f][0] for f in candidate.causal_fault_ids]
    events = {e.seq: e for e in record.events}

    if candidate.kind == "CLEAN":
        label = "CLEAN"
    elif candidate.kind == "DECOY_ONLY":
        if outcome is not Outcome.PASS:
            return Rejected(candidate.instance_id, "decoy alone changed the outcome (not harmless)")
        label = "DECOY_ONLY"
    else:
        label = "CAUSAL" if outcome is Outcome.FAIL else "MASKED"

    confirmed: bool | None = None
    if label == "CAUSAL" and len(injection_sites) == 1:
        result = intervene(
            record,
            ctx,
            InterventionRequest(
                injection_sites[0],
                OBS,
                ReferenceSource.INJECTION_CLEAN_VALUE,
                "validator: clean value at the injection site",
            ),
            allow_privileged=True,
        )
        confirmed = result.outcome is Outcome.PASS

    distance: int | None = None
    if injection_sites:
        start = tool_index_at_or_after(trace, injection_sites[0])
        end = tool_index_at_or_after(trace, symptom)
        if start is not None and end is not None:
            distance = end - start

    instance = {
        "instance_id": candidate.instance_id,
        "scenario_id": candidate.scenario_id,
        "split": candidate.split,
        "policy_version": POLICY_VERSION,
        "kind": candidate.kind,
        "fault_plan": candidate.fault_plan.model_dump(mode="json")
        if candidate.fault_plan
        else None,
    }
    labels = {
        "instance_id": candidate.instance_id,
        "split": candidate.split,
        "label": label,
        "kind": candidate.kind,
        "outcome": outcome.value,
        "operators": [operators[f] for f in candidate.causal_fault_ids],
        "injection_sites": [
            {"fault_id": f, "seq": sites[f][0], "logical_key": events[sites[f][0]].logical_key}
            for f in candidate.causal_fault_ids
        ],
        "decoy_sites": [sites[f][0] for f in candidate.decoy_fault_ids],
        "symptom_seq": symptom,
        "symptom_distance": distance,
        "expected_category": (
            EXPECTED_CATEGORY.get(operators[candidate.causal_fault_ids[0]])
            if len(candidate.causal_fault_ids) == 1
            else None
        ),
        "confirmed_by_clean_value": confirmed,
        "final_state_hash": record.footer.final_state_hash,
    }
    return Validated(instance, labels)
