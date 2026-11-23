"""Benchmark files: manifest, instances, labels (privileged), rejected (TRACE_SCHEMA §9)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agenttrace.bench.generate import (
    BENCHMARK_VERSION,
    GENERATOR_VERSION,
    POLICY_VERSION,
    SEED,
    generate_candidates,
)
from agenttrace.bench.validate import Rejected, Validated, validate_candidate
from agenttrace.env.support.scenario import list_scenario_ids, load_scenario
from agenttrace.env.support.tools import support_manifest_hash
from agenttrace.evals.oracle import ORACLE_REF
from agenttrace.policies.support_scripted import ScriptedSupportPolicy
from agenttrace.replay.exact import ReplayContext
from agenttrace.trace.canonical import canonical_bytes
from agenttrace.trace.fingerprint import fingerprint

DEFAULT_DIR = Path("benchmarks") / BENCHMARK_VERSION
SPLITS = {"dev": ["T1", "T2", "T3", "T4"], "test": ["T5", "T6", "T7", "T8"]}


@dataclass(frozen=True)
class BuildResult:
    instances: list[dict[str, Any]]
    labels: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    manifest: dict[str, Any]


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_bytes(r) + b"\n" for r in rows)


def build_benchmark(ctx: ReplayContext) -> BuildResult:
    instances: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in generate_candidates():
        result = validate_candidate(candidate, ctx)
        if isinstance(result, Rejected):
            rejected.append({"instance_id": result.instance_id, "reason": result.reason})
        else:
            assert isinstance(result, Validated)
            instances.append(result.instance)
            labels.append(result.label)
    counts = Counter(label["label"] for label in labels)
    by_split = Counter(f"{label['split']}:{label['label']}" for label in labels)
    manifest = {
        "benchmark_version": BENCHMARK_VERSION,
        "generator_version": GENERATOR_VERSION,
        "seed": SEED,
        "policy": {
            "policy_id": ScriptedSupportPolicy.policy_id,
            "policy_version": POLICY_VERSION,
            "source_hash": ScriptedSupportPolicy(POLICY_VERSION).source_hash,
        },
        "tool_manifest_hash": support_manifest_hash(),
        "oracle": {"id": ORACLE_REF.id, "version": ORACLE_REF.version},
        "scenarios": {sid: load_scenario(sid).initial_state_hash() for sid in list_scenario_ids()},
        "splits": SPLITS,
        "counts": {
            "instances": len(instances),
            "rejected": len(rejected),
            "by_label": dict(sorted(counts.items())),
            "by_split_label": dict(sorted(by_split.items())),
        },
        "files": {
            "instances.jsonl": fingerprint(instances),
            "labels.jsonl": fingerprint(labels),
            "rejected.jsonl": fingerprint(rejected),
        },
    }
    return BuildResult(instances, labels, rejected, manifest)


def write_benchmark(result: BuildResult, out_dir: Path = DEFAULT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "instances.jsonl").write_bytes(_jsonl(result.instances))
    (out_dir / "labels.jsonl").write_bytes(_jsonl(result.labels))
    (out_dir / "rejected.jsonl").write_bytes(_jsonl(result.rejected))
    (out_dir / "manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_instances(out_dir: Path = DEFAULT_DIR) -> list[dict[str, Any]]:
    return _read_jsonl(out_dir / "instances.jsonl")


def load_labels(out_dir: Path = DEFAULT_DIR) -> list[dict[str, Any]]:
    """PRIVILEGED: benchmark validator and metrics only. Localizers must never call this."""
    return _read_jsonl(out_dir / "labels.jsonl")


def verify_benchmark(ctx: ReplayContext, out_dir: Path = DEFAULT_DIR) -> list[str]:
    """Regenerate from scratch and compare with the files on disk. Returns problems (empty = ok)."""
    problems: list[str] = []
    fresh = build_benchmark(ctx)
    for name, rows in (
        ("instances.jsonl", fresh.instances),
        ("labels.jsonl", fresh.labels),
        ("rejected.jsonl", fresh.rejected),
    ):
        path = out_dir / name
        if not path.is_file():
            problems.append(f"missing {name}")
        elif path.read_bytes() != _jsonl(rows):
            problems.append(f"{name} differs from a fresh, deterministic regeneration")
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.is_file():
        problems.append("missing manifest.json")
    elif json.loads(manifest_path.read_text(encoding="utf-8")) != fresh.manifest:
        problems.append("manifest.json differs from a fresh regeneration")
    return problems
