"""End-to-end RECORD runs: oracles, determinism, isolation, no external side effects."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from agenttrace.env.support.scenario import list_scenario_ids, load_scenario
from agenttrace.runner import record_scenario
from agenttrace.trace.schema import Outcome, RunStatus
from agenttrace.trace.semantic import semantic_fingerprint
from agenttrace.trace.store import JsonlTraceStore

SCENARIOS = list_scenario_ids()
COMMITTED = {"T1", "T2", "T3", "T5", "T6"}


def test_committed_templates_present() -> None:
    assert set(SCENARIOS) >= COMMITTED
    for sid in SCENARIOS:
        scenario = load_scenario(sid)
        assert scenario.split == ("dev" if sid in {"T1", "T2", "T3", "T4"} else "test")


@pytest.mark.parametrize("policy", ["v1", "v2"])
@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_clean_scenarios_pass(scenario_id: str, policy: str) -> None:
    record = record_scenario(load_scenario(scenario_id), policy_version=policy)  # type: ignore[arg-type]
    assert record.footer.status is RunStatus.COMPLETED
    assert record.footer.outcome.outcome is Outcome.PASS, record.footer.outcome.violated_clauses


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_repeated_runs_have_identical_semantic_fingerprints(scenario_id: str) -> None:
    a = record_scenario(load_scenario(scenario_id))
    b = record_scenario(load_scenario(scenario_id))
    assert a.header.run_id != b.header.run_id
    assert {e.span_id for e in a.events}.isdisjoint({e.span_id for e in b.events})
    assert semantic_fingerprint(a) == semantic_fingerprint(b)
    assert a.footer.final_state_hash == b.footer.final_state_hash


def test_policy_versions_have_different_config_fingerprints() -> None:
    a = record_scenario(load_scenario("T1"), policy_version="v1")
    b = record_scenario(load_scenario("T1"), policy_version="v2")
    assert a.header.config_fingerprint != b.header.config_fingerprint


def test_interleaved_repeated_runs_do_not_leak_state() -> None:
    """Precursor of acceptance test #15 (record-only; replays arrive in Week 2)."""
    baseline = {sid: semantic_fingerprint(record_scenario(load_scenario(sid))) for sid in SCENARIOS}
    for _ in range(5):
        for sid in SCENARIOS:
            assert semantic_fingerprint(record_scenario(load_scenario(sid))) == baseline[sid]


def test_scenario_object_is_never_mutated() -> None:
    scenario = load_scenario("T1")
    before = scenario.initial_state_hash()
    record = record_scenario(scenario)
    assert scenario.initial_state_hash() == before
    assert record.footer.final_state_hash != before  # the run did change its own copy
    assert scenario.initial_state.refunds == {}


def test_runs_do_not_touch_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    for sid in SCENARIOS:
        assert record_scenario(load_scenario(sid)).footer.outcome.outcome is Outcome.PASS


def test_real_runs_roundtrip_through_store(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path)
    for sid in SCENARIOS:
        record = record_scenario(load_scenario(sid))
        store.save(record)
        loaded = store.load_record(record.header.run_id)
        assert loaded == record
        assert semantic_fingerprint(loaded) == semantic_fingerprint(record)
        assert store.load_trace(record.header.run_id) == record.observable()
    assert len(store.list_run_ids()) == len(SCENARIOS)
