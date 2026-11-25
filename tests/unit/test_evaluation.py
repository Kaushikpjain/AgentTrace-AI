"""Week 4: statistics, metrics on hand-built fixtures, held-out guard, evaluation leakage."""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from agenttrace.bench.metrics import compute_metrics, same_step_action
from agenttrace.bench.stats import (
    cluster_bootstrap_mean,
    dec,
    holm,
    mcnemar_exact,
    proportion,
    summary,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "agenttrace"


# ------------------------------------------------------------------ statistics
def test_proportion_and_wilson() -> None:
    p = proportion(8, 16)
    assert (p["k"], p["n"], p["rate"]) == (8, 16, Decimal("0.5"))
    assert p["ci95"] == [Decimal("0.28"), Decimal("0.72")]  # Wilson 95% for 8/16
    assert proportion(0, 0) == {"k": 0, "n": 0, "rate": None, "ci95": None}
    full = proportion(16, 16)
    assert full["ci95"][1] == Decimal("1") and full["ci95"][0] == Decimal("0.8064")  # type: ignore[index]


def test_mcnemar_exact_known_values() -> None:
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(8, 0) == pytest.approx(2 / 256)  # 2 * 0.5^8
    assert mcnemar_exact(3, 0) == pytest.approx(0.25)
    assert mcnemar_exact(5, 5) == 1.0


def test_holm_is_monotone_and_capped() -> None:
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert holm({"x": 0.9, "y": 0.8}) == {"x": 1.0, "y": 1.0}


def test_cluster_bootstrap_deterministic_and_bounds() -> None:
    values = [1.0, 0.0, 1.0, 1.0, 0.5, 0.0]
    clusters = ["T1", "T1", "T2", "T3", "T3", "T4"]
    a = cluster_bootstrap_mean(values, clusters, seed=0, resamples=500)
    b = cluster_bootstrap_mean(values, clusters, seed=0, resamples=500)
    assert a == b and a is not None and a[0] <= a[1]
    assert cluster_bootstrap_mean([], [], seed=0) is None
    assert cluster_bootstrap_mean([1.0, 1.0], ["T1", "T2"], seed=0, resamples=50) == (
        Decimal("1"),
        Decimal("1"),
    )


def test_summary_and_dec() -> None:
    assert summary([]) == {"n": 0, "mean": None, "median": None, "max": None, "total": 0}
    assert summary([1, 4, 2, 3]) == {
        "n": 4,
        "mean": Decimal("2.5"),
        "median": Decimal("2.5"),
        "max": 4,
        "total": 10,
    }
    assert dec(1 / 3) == Decimal("0.3333")


# ------------------------------------------------------------------ metrics on fixtures
def _step(seq: int, label: str = "SUSPICION", exp: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "seq": seq,
        "label": label,
        "score": 0,
        "note": "",
        "reference": None,
        "experiment": exp,
    }


def _exp(repair: bool, placebo_valid: bool = True) -> dict[str, Any]:
    return {
        "type": "EXECUTION_REPLACEMENT",
        "source": "REFERENCE_TOOL",
        "status": "COMPLETED",
        "outcome": "PASS" if repair else "FAIL",
        "placebo_status": "COMPLETED",
        "placebo_outcome": "FAIL",
        "placebo_valid": placebo_valid,
        "repair_observed": repair,
        "reason": None,
        "cassette_accesses_after_fence": 0,
    }


def _method(
    ranking: list[int], repair_sites: list[int] | None = None, labels: dict[int, str] | None = None
) -> dict[str, Any]:
    steps = [
        _step(
            s,
            (labels or {}).get(s, "SUSPICION"),
            _exp(s in (repair_sites or [])) if labels and s in labels else None,
        )
        for s in ranking
    ]
    return {
        "ranking": ranking,
        "steps": steps,
        "conclusion": "repair sites: x" if repair_sites else "NOT_ISOLATED",
        "repair_sites": repair_sites or [],
        "unsupported": [],
        "replays_used": 2 * len(ranking),
        "notes": [],
    }


def _result(iid: str, outcome: str, cf: dict[str, Any], b1: dict[str, Any]) -> dict[str, Any]:
    steps = {
        "4": {"boundary": "DECISION", "name": "decide", "step_index": 1},
        "5": {"boundary": "TOOL", "name": "get_order", "step_index": 1},
        "8": {"boundary": "TOOL", "name": "search_policy", "step_index": 2},
    }
    return {
        "instance_id": iid,
        "scenario_id": iid.split("-")[0],
        "split": "dev",
        "kind": "SINGLE",
        "original_outcome": outcome,
        "replay_verdict": "VERIFIED",
        "symptom_seq": 8,
        "candidates": [4, 5, 8],
        "steps": steps,
        "flags": {},
        "methods": {"CF": cf, "B1": b1},
    }


def _label(
    iid: str,
    label: str,
    site: int | None,
    operator: str = "WRONG_ARGUMENT",
    distance: int = 1,
    decoys: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "instance_id": iid,
        "label": label,
        "kind": "SINGLE",
        "split": "dev",
        "operators": [operator] if site is not None else [],
        "injection_sites": [{"seq": site, "fault_id": "f", "logical_key": "k"}] if site else [],
        "decoy_sites": decoys or [],
        "symptom_distance": distance,
    }


def _fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results = [
        _result(
            "T1-a",
            "FAIL",
            _method([4, 5, 8], [4], {4: "INTERVENTIONAL_REPAIR"}),
            _method([5, 4, 8]),
        ),
        _result(
            "T2-b",
            "FAIL",
            _method([8, 4, 5], [8], {8: "INTERVENTIONAL_REPAIR"}),
            _method([8, 4, 5]),
        ),
        _result("T3-c", "PASS", _method([4, 5, 8]), _method([4, 5, 8])),
    ]
    labels = [
        _label("T1-a", "CAUSAL", 4),
        _label("T2-b", "CAUSAL", 8, "WRONG_RETRIEVAL", 0),
        _label("T3-c", "MASKED", 5),
    ]
    return results, labels


def test_metrics_on_fixture() -> None:
    results, labels = _fixture()
    m = compute_metrics(results, [], labels, methods=["B1", "CF"], seed=0, resamples=200)
    assert m["population"]["eligible_for_metric_a"] == 2
    cf, b1 = m["metric_a"]["by_method"]["CF"], m["metric_a"]["by_method"]["B1"]
    assert (cf["top1"]["k"], cf["top1"]["n"]) == (2, 2)
    assert (b1["top1"]["k"], b1["top3"]["k"]) == (1, 2)
    assert b1["mrr"]["value"] == Decimal("0.75")  # ranks 2 and 1
    assert b1["top1_same_step_action"]["k"] == 2  # seq 5 is the decision's own tool call
    assert b1["by_operator"]["WRONG_ARGUMENT"]["top1"]["k"] == 0
    assert m["metric_a"]["random_reference_B0"]["expected_top1"] == Decimal("0.3333")
    paired = m["metric_a"]["paired_top1"]["comparisons"]["CF_vs_B1"]
    assert (paired["only_first_correct"], paired["only_second_correct"]) == (1, 0)
    b = m["metric_b"]
    assert (b["repair_success"]["k"], b["repair_success"]["n"]) == (2, 2)
    assert b["injected_site_repaired"]["k"] == 2
    assert b["placebo_validity"]["k"] == b["placebo_validity"]["n"] == 2
    assert m["checks"]["ok"] and m["checks"]["false_repairs_on_passing_runs"] == 0


def test_checks_flag_violations() -> None:
    results, labels = _fixture()
    results[2]["methods"]["CF"] = _method([4], [4], {4: "INTERVENTIONAL_REPAIR"})  # PASS run
    results[0]["methods"]["CF"]["steps"][0]["experiment"]["placebo_valid"] = False
    results[1]["replay_verdict"] = "DIVERGED"
    m = compute_metrics(
        results,
        [
            {
                "instance_id": "T1-a",
                "baseline_outcome": "FAIL",
                "verdict": "x",
                "comparison": "y",
                "passes": 0,
                "n": 2,
                "cassettes_constructed": 1,
            }
        ],
        labels,
        methods=["B1", "CF"],
        seed=0,
        resamples=50,
        benchmark_problems=["labels.jsonl differs"],
    )
    violations = " | ".join(m["checks"]["violations"])
    for text in (
        "strict replay",
        "placebo",
        "passing runs",
        "regression constructed",
        "benchmark: labels",
    ):
        assert text in violations
    assert not m["checks"]["ok"]


def test_missing_labels_rejected() -> None:
    results, labels = _fixture()
    with pytest.raises(ValueError, match="no labels"):
        compute_metrics(results, [], labels[:1], methods=["B1"], seed=0, resamples=10)


def test_same_step_action() -> None:
    results, _ = _fixture()
    assert same_step_action(results[0], 4) == {4, 5}
    assert same_step_action(results[0], 8) == {8}  # tool sites match only themselves


# held-out guard tests moved to tests/unit/test_heldout.py (hardened post-freeze, ADR-026)


# ------------------------------------------------------------------ leakage in the eval path
def test_evaluation_driver_never_reads_labels() -> None:
    tree = ast.parse((SRC / "bench" / "evaluate.py").read_text(encoding="utf-8"))
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "load_labels" not in names and "agenttrace.bench.validate" not in modules
    assert "agenttrace.bench.metrics" not in modules
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {"ledger", "load_ledger", "load_labels"}
