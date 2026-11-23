"""P4: single-field cassette mutations are never silently accepted.

(a) On disk: any mutated JSON leaf in events/ledger/header is rejected at load time.
(b) In memory, self-consistent mutations of tool-side facts are detected by strict replay.
Decision payloads are served (not recomputed) by strict replay, so (b) covers tool events;
decision tampering is covered by (a) (REPLAY_SPEC section 5.2, "Known limit").
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agenttrace.env.support.scenario import load_scenario
from agenttrace.replay.exact import ReplayVerdict, replay_strict
from agenttrace.runner import record_scenario, support_replay_context
from agenttrace.trace.schema import Boundary, RunRecord
from agenttrace.trace.store import JsonlTraceStore, TraceStoreError
from tests import plans
from tests.replay_helpers import map_event, map_ledger, revalidated

CTX = support_replay_context()
RECORDS = {
    "clean": record_scenario(load_scenario("T1")),
    "lost_ack": record_scenario(load_scenario("T1"), fault_plan=plans.lost_ack()),
}


def _leaves(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _leaves(v, (*path, k))]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _leaves(v, (*path, i))]
    return [path]


def _mutate_leaf(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "x"
    return "mutated"  # None


def _set(doc: Any, path: tuple[Any, ...], new: Any) -> None:
    for key in path[:-1]:
        doc = doc[key]
    doc[path[-1]] = new


@settings(max_examples=60)
@given(data=st.data(), which=st.sampled_from(sorted(RECORDS)))
def test_p4a_on_disk_mutation_rejected(data: st.DataObject, which: str) -> None:
    record = RECORDS[which]
    with tempfile.TemporaryDirectory() as tmp:
        _check_on_disk_mutation(Path(tmp), data, record)


def _check_on_disk_mutation(root: Path, data: st.DataObject, record: RunRecord) -> None:
    store = JsonlTraceStore(root)
    store.save(record)
    run_dir = root / record.header.run_id
    file = data.draw(st.sampled_from(["header.json", "events.jsonl", "ledger.jsonl"]))
    path = run_dir / file
    if file.endswith(".jsonl"):
        lines = path.read_text().splitlines()
        index = data.draw(st.integers(0, len(lines) - 1))
        doc = json.loads(lines[index])
        leaf = data.draw(st.sampled_from(_leaves(doc)))
        _set(doc, leaf, _mutate_leaf(_get(doc, leaf)))
        lines[index] = json.dumps(doc)
        path.write_text("\n".join(lines) + "\n")
    else:
        doc = json.loads(path.read_text())
        leaf = data.draw(st.sampled_from(_leaves(doc)))
        _set(doc, leaf, _mutate_leaf(_get(doc, leaf)))
        path.write_text(json.dumps(doc))
    with pytest.raises(TraceStoreError):
        store.load_record(record.header.run_id)


def _get(doc: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        doc = doc[key]
    return doc


def _tool_events(record: RunRecord) -> list[Any]:
    return [e for e in record.events if e.boundary is Boundary.TOOL]


@settings(max_examples=60)
@given(data=st.data(), which=st.sampled_from(sorted(RECORDS)))
def test_p4b_self_consistent_tool_mutation_detected_by_replay(
    data: st.DataObject, which: str
) -> None:
    record = RECORDS[which]
    event = data.draw(st.sampled_from(_tool_events(record)))
    target = data.draw(st.sampled_from(["response", "raw_output", "state"]))
    if target == "response":
        leaf = data.draw(st.sampled_from(_leaves(event.response)))
        new = json.loads(json.dumps(event.response))
        _set(new, leaf, _mutate_leaf(_get(new, leaf)))
        tampered = map_event(record, event.seq, lambda e: revalidated(e, response=new))
    elif target == "raw_output":
        entry = next(x for x in record.ledger if x.seq == event.seq)
        if entry.raw_output is None:
            new_raw: Any = {"status": "OK", "data": {}, "error": None}
            tampered = map_ledger(
                record, event.seq, lambda x: revalidated(x, raw_output=new_raw, executed=True)
            )
        else:
            leaf = data.draw(st.sampled_from(_leaves(entry.raw_output)))
            new_raw = json.loads(json.dumps(entry.raw_output))
            _set(new_raw, leaf, _mutate_leaf(_get(new_raw, leaf)))
            tampered = map_ledger(record, event.seq, lambda x: revalidated(x, raw_output=new_raw))
    else:
        state = event.state
        assert state is not None
        if state.committed:
            new_state = state.model_copy(update={"after_hash": "sha256:" + "e" * 64})
        else:
            fake = "sha256:" + "d" * 64
            new_state = state.model_copy(update={"before_hash": fake, "after_hash": fake})
        tampered = map_event(record, event.seq, lambda e: e.model_copy(update={"state": new_state}))
    report = replay_strict(tampered, CTX)
    assert report.verdict is ReplayVerdict.DIVERGED
    assert report.divergence is not None and report.divergence.seq <= event.seq
