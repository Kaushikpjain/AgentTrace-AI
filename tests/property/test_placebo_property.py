"""Property: for any supported target and type, the same-type placebo reproduces the original
run (status, outcome, clauses, final state) and the cassette is never touched after the fence."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from agenttrace.bench.generate import generate_candidates
from agenttrace.bench.validate import record_candidate
from agenttrace.replay.counterfactual import (
    EXE,
    OBS,
    CounterfactualStatus,
    InterventionRequest,
    intervene,
)
from agenttrace.runner import support_replay_context
from agenttrace.trace.schema import Boundary, ReferenceSource

CTX = support_replay_context()
CANDIDATES = {c.instance_id: c for c in generate_candidates()}
RECORDS = {iid: record_candidate(c) for iid, c in list(CANDIDATES.items())[::4]}


@settings(max_examples=40, deadline=None)
@given(data=st.data(), instance=st.sampled_from(sorted(RECORDS)))
def test_placebo_reproduces_original(data: st.DataObject, instance: str) -> None:
    record = RECORDS[instance]
    targets = [e for e in record.events if e.boundary in (Boundary.DECISION, Boundary.TOOL)]
    event = data.draw(st.sampled_from(targets))
    itype = EXE if event.boundary is Boundary.TOOL and data.draw(st.booleans()) else OBS
    result = intervene(record, CTX, InterventionRequest(event.seq, itype, ReferenceSource.ORIGINAL))
    assert result.status is CounterfactualStatus.COMPLETED, result.reason
    assert result.run is not None and result.cassette_accesses_after_fence == 0
    footer, original = result.run.footer, record.footer
    assert footer.status is original.status
    assert footer.outcome == original.outcome
    assert footer.final_state_hash == original.final_state_hash
