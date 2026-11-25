"""Week 4: `bench run` on a small subset: byte-identical canonical outputs, checks, CLI guard."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agenttrace.bench.io import DEFAULT_DIR, load_instances, load_labels
from agenttrace.bench.run import run_benchmark
from agenttrace.cli import app
from agenttrace.runner import support_replay_context

REPO = Path(__file__).resolve().parents[2]
CANONICAL = (
    "metrics.json",
    "config.json",
    "results.jsonl",
    "table.md",
    "failure_cases.md",
    "canonical_fingerprints.json",
)
SUBSET = ("T1-clean", "T1-F2-order", "T1-F4", "T1-F5", "T1-D1", "T1-D1+F4", "T2-F4")


@pytest.fixture(scope="module")
def subset() -> list[dict]:  # type: ignore[type-arg]
    return [i for i in load_instances(REPO / DEFAULT_DIR) if i["instance_id"] in SUBSET]


def _run(out: Path, instances: list[dict]) -> dict:  # type: ignore[type-arg]
    return run_benchmark(
        split="dev",
        ctx=support_replay_context(),
        out_dir=out,
        instances=instances,
        labels=load_labels(REPO / DEFAULT_DIR),
        bench_dir=REPO / DEFAULT_DIR,
        check_regeneration=False,
    )


def test_canonical_outputs_are_byte_identical(tmp_path: Path, subset: list[dict]) -> None:  # type: ignore[type-arg]
    first = _run(tmp_path / "a", subset)
    second = _run(tmp_path / "b", subset)
    assert first == second
    for name in CANONICAL:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    for volatile in ("environment.json", "timings.json"):
        assert (tmp_path / "a" / volatile).is_file()
    assert "run_id" not in (tmp_path / "a" / "metrics.json").read_text()
    assert "started_at" not in (tmp_path / "a" / "metrics.json").read_text()


def test_subset_checks_and_metrics(tmp_path: Path, subset: list[dict]) -> None:  # type: ignore[type-arg]
    metrics = _run(tmp_path / "m", subset)
    checks = metrics["checks"]
    assert checks["ok"], checks["violations"]
    assert checks["strict_replay_verified"]["k"] == len(subset)
    assert checks["false_repairs_on_passing_runs"] == 0
    assert checks["regression_cassettes_constructed"] == 0
    a = metrics["metric_a"]["by_method"]
    assert set(a) == {"B1", "B3", "B4", "CF"}
    n = {m: a[m]["top1"]["n"] for m in a}
    assert len(set(n.values())) == 1 and n["CF"] == 4  # same eligible set for every method
    assert a["CF"]["top1"]["k"] == 4
    assert a["B4"]["decoy_false_attribution"]["k"] == 1  # T1-D1+F4
    table = (tmp_path / "m" / "table.md").read_text()
    assert "not unique causal attribution" in table and "4/4" in table


def test_cli_refuses_test_split_without_guards(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["bench", "run", "--split", "test", "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert "Refusing to run the held-out test split" in result.output
    assert "missing --confirm-single-test-run" in result.output
    assert not any(tmp_path.iterdir())  # nothing evaluated or written


def test_cli_rejects_bad_options(tmp_path: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["bench", "run", "--split", "x"]).exit_code == 2
    assert runner.invoke(app, ["bench", "run", "--methods", "ZZ"]).exit_code == 2


def test_passing_runs_conclude_no_failure_without_false_repairs(
    tmp_path: Path,
    subset: list[dict],  # type: ignore[type-arg]
) -> None:
    import json

    metrics = _run(tmp_path / "p", subset)
    rows = [
        json.loads(line) for line in (tmp_path / "p" / "results.jsonl").read_text().splitlines()
    ]
    passing = [r for r in rows if r["original_outcome"] == "PASS"]
    assert passing, "subset must contain passing runs"
    for row in passing:
        assert row["methods"]["CF"]["conclusion"] == "NO_FAILURE", row["instance_id"]
        assert row["methods"]["CF"]["repair_sites"] == []
    for row in rows:
        if row["original_outcome"] == "FAIL":
            assert row["methods"]["CF"]["conclusion"] != "NO_FAILURE"
    assert metrics["checks"]["false_repairs_on_passing_runs"] == 0


def test_cli_test_split_refused_even_with_flags_after_freeze(tmp_path: Path) -> None:
    log = REPO / "evaluation" / "TEST_RUNS.log"
    before = log.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "run",
            "--split",
            "test",
            "--confirm-single-test-run",
            "--approved-commit",
            "eb6d95c19d0ae886cef1b0ae4fca431d6fa29a50",
        ],
        terminal_width=200,
    )
    assert result.exit_code == 2, result.output
    assert "Refusing to run the held-out test split" in result.output
    assert log.read_bytes() == before
    repro = CliRunner().invoke(
        app, ["bench", "run", "--split", "dev", "--reproducibility-check", "--out", str(tmp_path)]
    )
    assert repro.exit_code == 2 and "only valid with --split test" in repro.output
