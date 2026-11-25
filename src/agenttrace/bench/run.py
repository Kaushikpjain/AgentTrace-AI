"""`atrace bench run`: reproducible evaluation with separated canonical and volatile outputs.

Canonical (byte-identical across repeated runs of the same configuration):
  metrics.json, config.json, table.md, failure_cases.md, results.jsonl
Volatile (expected to differ between runs; never compared):
  environment.json (timestamp, run id, git state, versions), timings.json (wall time, RSS)

Held-out protection (``agenttrace.bench.heldout``): the ``test`` split requires a
``HeldOutAuthorization`` (approved commit, annotated freeze tag resolving to it, HEAD at it,
clean tree, frozen config fingerprint, explicit confirmation). Every authorized test-split run
appends one entry to ``evaluation/TEST_RUNS.log`` with command, exit status, commit,
config fingerprint, run id, timestamps and artifact fingerprints.
"""

from __future__ import annotations

import json
import platform
import resource
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from agenttrace import __version__
from agenttrace.bench.evaluate import METHODS, evaluate_split
from agenttrace.bench.generate import BENCHMARK_VERSION, POLICY_VERSION
from agenttrace.bench.heldout import (
    HeldOutAuthorization,
    append_log,
    git_output,
    require_authorization,
)
from agenttrace.bench.io import DEFAULT_DIR, load_instances, load_labels, verify_benchmark
from agenttrace.bench.metrics import compute_metrics
from agenttrace.bench.report import render_failures, render_table
from agenttrace.localize.baselines import W_CHAIN, W_ERROR, W_FLAG, W_MUTATING
from agenttrace.replay.exact import ReplayContext
from agenttrace.trace.canonical import canonical_bytes
from agenttrace.trace.fingerprint import fingerprint

SEED = 0
RESAMPLES = 2000
EVALUATION_DIR = Path("evaluation")
TEST_LOG = EVALUATION_DIR / "TEST_RUNS.log"


def experiment_config(split: str, methods: Sequence[str], bench_dir: Path) -> dict[str, Any]:
    manifest = json.loads((bench_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_manifest_fp": fingerprint(manifest),
        "split": split,
        "methods": list(methods),
        "agent_policy_version": POLICY_VERSION,
        "b3_weights": {"chain": W_CHAIN, "flag": W_FLAG, "error": W_ERROR, "mutating": W_MUTATING},
        "statistics": {
            "proportion_ci": "Wilson 95%",
            "mrr_ci": "percentile bootstrap over templates",
            "bootstrap_seed": SEED,
            "bootstrap_resamples": RESAMPLES,
            "paired_test": "exact McNemar (two-sided), Holm-adjusted",
        },
        "eligibility": "label CAUSAL with exactly one injection site",
        "code": {
            "tool_manifest_hash": manifest["tool_manifest_hash"],
            "policy_source_hash": manifest["policy"]["source_hash"],
            "oracle": manifest["oracle"],
        },
    }


def _environment(run_id: str) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in ("pydantic", "typer", "rich"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "agenttrace_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": packages,
        "git_head": git_output(["rev-parse", "HEAD"]),
        "git_dirty": bool(git_output(["status", "--porcelain"])),
    }


def _peak_rss_bytes() -> int:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == "darwin" else raw * 1024)


def _jsonl(rows: Sequence[dict[str, Any]]) -> bytes:
    return b"".join(canonical_bytes(r) + b"\n" for r in rows)


def run_benchmark(
    *,
    split: str,
    ctx: ReplayContext,
    out_dir: Path,
    methods: Sequence[str] = METHODS,
    bench_dir: Path = DEFAULT_DIR,
    check_regeneration: bool = True,
    instances: Sequence[dict[str, Any]] | None = None,
    labels: Sequence[dict[str, Any]] | None = None,
    authorization: HeldOutAuthorization | None = None,
    log_path: Path = TEST_LOG,
) -> dict[str, Any]:
    """Run one split and write outputs. Returns the canonical metrics dict.

    The test split raises ``HeldOutAccessError`` without a ``HeldOutAuthorization`` and
    appends one log entry per authorized run, including failed ones.
    """
    if split not in ("dev", "test"):
        raise ValueError("split must be 'dev' or 'test'")
    require_authorization(split, authorization)
    run_id = uuid.uuid4().hex
    environment = _environment(run_id)

    def execute() -> tuple[dict[str, Any], dict[str, str]]:
        return _evaluate_and_write(
            split=split,
            ctx=ctx,
            out_dir=out_dir,
            methods=methods,
            bench_dir=bench_dir,
            check_regeneration=check_regeneration,
            instances=instances,
            labels=labels,
            authorization=authorization,
            run_id=run_id,
            environment=environment,
        )

    if split != "test":
        return execute()[0]
    assert authorization is not None  # enforced by require_authorization
    exit_status: int | str = "error"
    canonical: dict[str, str] | None = None
    try:
        metrics, canonical = execute()
        exit_status = 0 if metrics["checks"]["ok"] else 1
        return metrics
    except BaseException as exc:
        exit_status = f"error: {type(exc).__name__}"
        raise
    finally:
        append_log(
            log_path,
            {
                "kind": "reproducibility_check"
                if authorization.reproducibility_check
                else "official",
                "command": authorization.command,
                "exit_status": exit_status,
                "started_at": environment["started_at"],
                "finished_at": datetime.now(UTC).isoformat(),
                "git_head": environment["git_head"],
                "git_dirty": environment["git_dirty"],
                "approved_commit": authorization.commit,
                "freeze_tag": authorization.tag,
                "config_fp": authorization.config_fp,
                "run_id": run_id,
                "out_dir": str(out_dir),
                "artifact_fps": canonical,
                "metrics_fp": canonical["metrics.json"] if canonical else None,
            },
        )


def _evaluate_and_write(
    *,
    split: str,
    ctx: ReplayContext,
    out_dir: Path,
    methods: Sequence[str],
    bench_dir: Path,
    check_regeneration: bool,
    instances: Sequence[dict[str, Any]] | None,
    labels: Sequence[dict[str, Any]] | None,
    authorization: HeldOutAuthorization | None,
    run_id: str,
    environment: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    t0 = time.perf_counter()
    all_instances = list(instances) if instances is not None else load_instances(bench_dir)
    results, regressions = evaluate_split(
        all_instances, split, ctx, methods, authorization=authorization
    )
    t_eval = time.perf_counter() - t0
    split_ids = {r["instance_id"] for r in results}
    all_labels = labels if labels is not None else load_labels(bench_dir)
    split_labels = [label for label in all_labels if label["instance_id"] in split_ids]
    problems = verify_benchmark(ctx, bench_dir) if check_regeneration else []
    metrics = compute_metrics(
        results,
        regressions,
        split_labels,
        methods=methods,
        seed=SEED,
        resamples=RESAMPLES,
        benchmark_problems=problems,
    )
    config = experiment_config(split, methods, bench_dir)
    config["regeneration_check"] = check_regeneration
    labels_by_id = {label["instance_id"]: label for label in split_labels}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_bytes(canonical_bytes(metrics) + b"\n")
    (out_dir / "config.json").write_bytes(canonical_bytes(config) + b"\n")
    (out_dir / "results.jsonl").write_bytes(_jsonl(results))
    (out_dir / "table.md").write_text(render_table(metrics, config), encoding="utf-8")
    (out_dir / "failure_cases.md").write_text(
        render_failures(results, labels_by_id, methods), encoding="utf-8"
    )
    timings = {
        "run_id": run_id,
        "evaluation_seconds": round(time.perf_counter() - t0, 3),
        "localization_and_regression_seconds": round(t_eval, 3),
        "instances": len(results),
        "peak_rss_bytes": _peak_rss_bytes(),
    }
    (out_dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    (out_dir / "timings.json").write_text(json.dumps(timings, indent=2) + "\n")
    canonical = {
        name: fingerprint((out_dir / name).read_bytes().decode("utf-8"))
        for name in ("metrics.json", "config.json", "results.jsonl", "table.md", "failure_cases.md")
    }
    (out_dir / "canonical_fingerprints.json").write_bytes(canonical_bytes(canonical) + b"\n")
    return metrics, canonical
