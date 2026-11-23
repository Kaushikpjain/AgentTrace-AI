from __future__ import annotations

import pytest

from agenttrace.env.support.scenario import load_scenario
from agenttrace.replay.cassette import Cassette, CassetteFenceViolation
from agenttrace.replay.exact import LiveCallAttempted, ReplayPolicyGuard, check_config
from agenttrace.replay.fidelity import compute_fidelity
from agenttrace.runner import record_scenario, support_replay_context
from agenttrace.runtime.gateway import DivergenceDetected
from agenttrace.trace.schema import Boundary, DivergenceKind, FaultPlan, FaultSpec, FaultStage
from agenttrace.trace.schema import FaultTrigger as Trigger
from tests import plans


@pytest.fixture(scope="module")
def record():  # type: ignore[no-untyped-def]
    return record_scenario(load_scenario("T1"))


def _boundary_events(record):  # type: ignore[no-untyped-def]
    return [e for e in record.events if e.boundary in (Boundary.DECISION, Boundary.TOOL)]


def test_cassette_serves_in_order_and_once(record) -> None:  # type: ignore[no-untyped-def]
    cassette = Cassette(record)
    events = _boundary_events(record)
    assert len(cassette) == len(events) == len(record.ledger)
    for event in events:
        entry = cassette.expect(event.seq, event.boundary, event.name, event.request_fp)
        assert entry.event == event
    assert cassette.remaining == 0 and cassette.accesses == len(events)
    with pytest.raises(DivergenceDetected) as info:
        cassette.expect(99, Boundary.DECISION, "decide", "sha256:x")
    assert info.value.divergence.kind is DivergenceKind.MISSING_EVENT


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"boundary": Boundary.TOOL}, DivergenceKind.BOUNDARY),
        ({"seq": 5}, DivergenceKind.BOUNDARY),
        ({"name": "other"}, DivergenceKind.NAME),
        ({"request_fp": "sha256:other"}, DivergenceKind.REQUEST),
    ],
)
def test_cassette_mismatches(record, change: dict, kind: DivergenceKind) -> None:  # type: ignore[no-untyped-def, type-arg]
    first = _boundary_events(record)[0]
    request = {
        "seq": first.seq,
        "boundary": first.boundary,
        "name": first.name,
        "request_fp": first.request_fp,
        **change,
    }
    cassette = Cassette(record)
    with pytest.raises(DivergenceDetected) as info:
        cassette.expect(**request)
    assert info.value.divergence.kind is kind
    assert cassette.position == 0  # nothing consumed on mismatch


def test_cassette_fence(record) -> None:  # type: ignore[no-untyped-def]
    cassette = Cassette(record)
    cassette.close()
    first = _boundary_events(record)[0]
    with pytest.raises(CassetteFenceViolation):
        cassette.expect(first.seq, first.boundary, first.name, first.request_fp)


def test_guard_policy_never_decides(record) -> None:  # type: ignore[no-untyped-def]
    guard = ReplayPolicyGuard(record.header.agent)
    assert (guard.policy_id, guard.policy_version) == (
        record.header.agent.policy_id,
        record.header.agent.policy_version,
    )
    with pytest.raises(LiveCallAttempted):
        guard.decide(None, ())
    assert guard.calls == 1


def test_check_config_fault_plan_unavailable_and_unreplayable(record) -> None:  # type: ignore[no-untyped-def]
    ctx = support_replay_context()
    faulty = record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack())
    assert check_config(faulty.header, faulty.fault_plan, ctx).ok
    missing = check_config(faulty.header, None, ctx)
    assert any("unavailable" in m for m in missing.mismatches)
    bogus = FaultPlan(
        plan_id="b",
        faults=(
            FaultSpec(
                fault_id="x",
                operator="BOGUS",
                stage=FaultStage.POST_EXECUTION,
                trigger=Trigger(boundary=Boundary.TOOL, name="get_order", occurrence=1),
            ),
        ),
    )
    assert any("not replayable" in m for m in check_config(faulty.header, bogus, ctx).mismatches)
    assert check_config(record.header, None, ctx).ok


def test_fidelity_of_record_against_itself(record) -> None:  # type: ignore[no-untyped-def]
    report = compute_fidelity(record, record)
    assert report.exact
    n = len(_boundary_events(record))
    assert (report.response_equality.matched, report.response_equality.total) == (n, n)
    assert str(report.raw_result_agreement) == "5/5"
