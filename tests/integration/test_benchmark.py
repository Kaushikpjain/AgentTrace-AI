"""Benchmark generation and validation (AgentTrace-Synth v0)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from agenttrace.bench.generate import generate_candidates
from agenttrace.bench.io import (
    DEFAULT_DIR,
    SPLITS,
    BuildResult,
    build_benchmark,
    load_instances,
    load_labels,
    verify_benchmark,
    write_benchmark,
)
from agenttrace.runner import support_replay_context

CTX = support_replay_context()
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built() -> BuildResult:
    return build_benchmark(CTX)


def test_generation_is_deterministic(built: BuildResult) -> None:
    again = build_benchmark(CTX)
    assert again.instances == built.instances and again.labels == built.labels
    assert again.manifest == built.manifest
    ids = [c.instance_id for c in generate_candidates()]
    assert len(ids) == len(set(ids))


def test_committed_benchmark_files_match_regeneration() -> None:
    assert verify_benchmark(CTX, REPO / DEFAULT_DIR) == []


def test_verify_detects_tampering(tmp_path: Path, built: BuildResult) -> None:
    write_benchmark(built, tmp_path)
    assert verify_benchmark(CTX, tmp_path) == []
    labels = (tmp_path / "labels.jsonl").read_text().replace('"CAUSAL"', '"MASKED"', 1)
    (tmp_path / "labels.jsonl").write_text(labels)
    assert any("labels.jsonl" in p for p in verify_benchmark(CTX, tmp_path))


def test_labels_are_validated(built: BuildResult) -> None:
    labels = built.labels
    counts = Counter(label["label"] for label in labels)
    assert counts["CLEAN"] == 8 and counts["DECOY_ONLY"] == 8
    assert counts["CAUSAL"] >= 30 and counts["MASKED"] >= 1
    for label in labels:
        if label["label"] in ("CLEAN", "DECOY_ONLY"):
            assert label["outcome"] == "PASS"
        if label["label"] == "CAUSAL":
            assert label["outcome"] == "FAIL"
        if label["label"] == "MASKED":
            assert label["outcome"] == "PASS"
        if label["label"] == "CAUSAL" and label["kind"] != "MULTI":
            assert label["confirmed_by_clean_value"] is True
            assert len(label["injection_sites"]) == 1 and label["expected_category"]
        if label["kind"] == "MULTI":
            assert len(label["injection_sites"]) == 2
    delayed = [x for x in labels if x["label"] == "CAUSAL" and (x["symptom_distance"] or 0) >= 1]
    assert len(delayed) >= 8


def test_split_by_template_without_leakage(built: BuildResult) -> None:
    assert set(SPLITS["dev"]).isdisjoint(SPLITS["test"])
    for instance in built.instances:
        expected = "dev" if instance["scenario_id"] in SPLITS["dev"] else "test"
        assert instance["split"] == expected


def test_instances_file_carries_no_labels(built: BuildResult) -> None:
    label_keys = {
        "label",
        "injection_sites",
        "decoy_sites",
        "symptom_seq",
        "expected_category",
        "confirmed_by_clean_value",
        "operators",
    }
    for instance in built.instances:
        assert not label_keys & set(instance)


def test_on_disk_loaders_roundtrip() -> None:
    instances = load_instances(REPO / DEFAULT_DIR)
    labels = load_labels(REPO / DEFAULT_DIR)
    assert [i["instance_id"] for i in instances] == [label["instance_id"] for label in labels]
