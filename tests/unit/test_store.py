from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrace.trace.store import (
    CorruptTraceError,
    IncompleteRecordingError,
    JsonlTraceStore,
    RunExistsError,
    RunNotFoundError,
    TraceIntegrityError,
    TraceSchemaError,
    TraceStoreError,
)
from tests.helpers import make_record


@pytest.fixture
def store(tmp_path: Path) -> JsonlTraceStore:
    return JsonlTraceStore(tmp_path / "runs")


def _saved(store: JsonlTraceStore, run_id: str = "run-test-1") -> Path:
    store.save(make_record(run_id))
    return store.root / run_id


def test_roundtrip(store: JsonlTraceStore) -> None:
    record = make_record()
    store.save(record)
    assert store.load_record(record.header.run_id) == record
    assert store.load_trace(record.header.run_id) == record.observable()
    assert store.load_ledger(record.header.run_id) == record.ledger
    assert store.list_run_ids() == [record.header.run_id]
    assert store.exists(record.header.run_id)


def test_no_temp_dirs_left_and_hidden_dirs_ignored(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "events.jsonl",
        "footer.json",
        "header.json",
        "ledger.jsonl",
    ]
    (store.root / ".tmp-crashed-1234").mkdir()
    assert store.list_run_ids() == ["run-test-1"]


def test_recordings_are_immutable(store: JsonlTraceStore) -> None:
    _saved(store)
    with pytest.raises(RunExistsError):
        store.save(make_record())


def test_missing_run(store: JsonlTraceStore) -> None:
    with pytest.raises(RunNotFoundError):
        store.load_trace("run-nope")


def test_invalid_run_id_rejected(store: JsonlTraceStore) -> None:
    with pytest.raises(TraceStoreError):
        store.load_trace("../etc")


def test_incomplete_recording(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    (run_dir / "footer.json").unlink()
    with pytest.raises(IncompleteRecordingError):
        store.load_trace("run-test-1")


def test_missing_events_file(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    (run_dir / "events.jsonl").unlink()
    with pytest.raises(CorruptTraceError, match="missing events"):
        store.load_trace("run-test-1")


def test_corrupted_event_line_invalid_json(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "events.jsonl"
    lines = path.read_text().splitlines()
    lines[1] = lines[1][:-5]  # truncate a line
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(CorruptTraceError, match=r"events\.jsonl:2"):
        store.load_trace("run-test-1")


def test_tampered_event_detected(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "events.jsonl"
    lines = path.read_text().splitlines()
    event = json.loads(lines[0])
    event["step_index"] = 7  # valid schema, but content changed
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(TraceIntegrityError, match="hash chain"):
        store.load_trace("run-test-1")


def test_tampered_payload_fp_detected(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "events.jsonl"
    lines = path.read_text().splitlines()
    event = json.loads(lines[2])
    event["response"]["data"]["refund_id"] = "R-9999"
    lines[2] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(TraceSchemaError, match="response_fp"):
        store.load_trace("run-test-1")


def test_missing_field(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "events.jsonl"
    lines = path.read_text().splitlines()
    event = json.loads(lines[0])
    del event["logical_key"]
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(TraceSchemaError, match=r"events\.jsonl:1"):
        store.load_trace("run-test-1")


def test_invalid_schema_value(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "footer.json"
    footer = json.loads(path.read_text())
    footer["status"] = "SOMETHING_ELSE"
    path.write_text(json.dumps(footer))
    with pytest.raises(TraceSchemaError, match=r"footer\.json"):
        store.load_trace("run-test-1")


def test_unsupported_schema_major(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "header.json"
    header = json.loads(path.read_text())
    header["schema_version"] = "2.0"
    path.write_text(json.dumps(header))
    with pytest.raises(TraceSchemaError, match="not supported"):
        store.load_trace("run-test-1")


def test_truncated_recording_detected(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    path = run_dir / "events.jsonl"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n")  # drop the last event
    with pytest.raises(TraceIntegrityError):
        store.load_trace("run-test-1")


def test_header_run_id_must_match_directory(store: JsonlTraceStore) -> None:
    run_dir = _saved(store)
    run_dir.rename(store.root / "run-renamed")
    with pytest.raises(TraceIntegrityError, match="directory"):
        store.load_trace("run-renamed")


def test_save_rejects_inconsistent_record(store: JsonlTraceStore) -> None:
    record = make_record()
    broken = record.model_copy(update={"ledger": record.ledger[:1]})
    with pytest.raises(TraceIntegrityError):
        store.save(broken)
    assert store.list_run_ids() == []
