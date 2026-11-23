"""Metric A/B/C and correctness checks (docs/EVALUATION.md). PRIVILEGED: joins labels.

Every rate carries its numerator and denominator. All methods are compared on the identical
eligible set: CAUSAL instances with exactly one injection site (MULTI instances are reported
separately). Injection-site localization is a match against *where the fault was injected*;
it is not a unique causal attribution.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from agenttrace.bench.stats import (
    cluster_bootstrap_mean,
    dec,
    holm,
    mcnemar_exact,
    proportion,
    summary,
)

PAIRED = (("CF", "B4"), ("CF", "B1"), ("B4", "B1"))
LABELS = ("SUSPICION", "REFERENCE_DEVIATION", "INTERVENTIONAL_REPAIR", "UNSUPPORTED")


def _rank(ranking: Sequence[int], seq: int) -> int | None:
    return ranking.index(seq) + 1 if seq in ranking else None


def _bucket(distance: int | None) -> str:
    if distance is None:
        return "unknown"
    return "0" if distance == 0 else ">=1"


def same_step_action(result: dict[str, Any], site: int) -> set[int]:
    """The injection site plus, for a DECISION site, the tool call issued in the same step.

    Secondary (lenient) match added during the dev review: a decision fault's first visible
    effect is the tool call it issues, which B1/B3 rank by design. The strict site match stays
    the primary Metric A.
    """
    steps = result["steps"]
    accepted = {site}
    info = steps.get(str(site))
    if info and info["boundary"] == "DECISION":
        accepted |= {
            int(seq)
            for seq, other in steps.items()
            if other["boundary"] == "TOOL" and other["step_index"] == info["step_index"]
        }
    return accepted


def eligible(labels: dict[str, dict[str, Any]], results: Sequence[dict[str, Any]]) -> list[str]:
    return [
        r["instance_id"]
        for r in results
        if labels[r["instance_id"]]["label"] == "CAUSAL"
        and len(labels[r["instance_id"]]["injection_sites"]) == 1
    ]


def _localization(
    method: str,
    ids: Sequence[str],
    by_id: dict[str, dict[str, Any]],
    labels: dict[str, Any],
    seed: int,
    resamples: int,
) -> dict[str, Any]:
    top1 = top3 = action_top1 = 0
    reciprocal: list[float] = []
    clusters: list[str] = []
    by_operator: dict[str, list[int | None]] = {}
    by_distance: dict[str, list[int | None]] = {}
    decoy_k = decoy_n = 0
    unranked = 0
    for iid in ids:
        label = labels[iid]
        site = label["injection_sites"][0]["seq"]
        ranking = by_id[iid]["methods"][method]["ranking"]
        rank = _rank(ranking, site)
        unranked += rank is None
        top1 += rank == 1
        top3 += rank is not None and rank <= 3
        action_top1 += bool(ranking) and ranking[0] in same_step_action(by_id[iid], site)
        reciprocal.append(1.0 / rank if rank else 0.0)
        clusters.append(by_id[iid]["scenario_id"])
        by_operator.setdefault(label["operators"][0], []).append(rank)
        by_distance.setdefault(_bucket(label["symptom_distance"]), []).append(rank)
        if label["decoy_sites"]:
            decoy_n += 1
            decoy_k += bool(ranking) and ranking[0] in label["decoy_sites"]

    def group(ranks: list[int | None]) -> dict[str, Any]:
        n = len(ranks)
        return {
            "top1": proportion(sum(r == 1 for r in ranks), n),
            "top3": proportion(sum(r is not None and r <= 3 for r in ranks), n),
        }

    n = len(ids)
    return {
        "top1": proportion(top1, n),
        "top3": proportion(top3, n),
        "mrr": {
            "value": dec(sum(reciprocal) / n) if n else None,
            "ci95_cluster_bootstrap": cluster_bootstrap_mean(
                reciprocal, clusters, seed=seed, resamples=resamples
            ),
            "n": n,
        },
        "top1_same_step_action": proportion(action_top1, n),
        "injection_site_not_ranked": unranked,
        "by_operator": {op: group(r) for op, r in sorted(by_operator.items())},
        "by_symptom_distance": {b: group(r) for b, r in sorted(by_distance.items())},
        "decoy_false_attribution": proportion(decoy_k, decoy_n),
    }


def _random_reference(ids: Sequence[str], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """B0: analytical expectation of a uniformly random ranking over the same candidates."""
    sizes = [len(by_id[i]["candidates"]) for i in ids]
    if not sizes:
        return {"n": 0}
    return {
        "n": len(sizes),
        "expected_top1": dec(sum(1 / s for s in sizes) / len(sizes)),
        "expected_top3": dec(sum(min(3, s) / s for s in sizes) / len(sizes)),
        "expected_mrr": dec(
            sum(sum(1 / k for k in range(1, s + 1)) / s for s in sizes) / len(sizes)
        ),
        "mean_candidates": dec(sum(sizes) / len(sizes)),
    }


def _paired(
    ids: Sequence[str],
    by_id: dict[str, dict[str, Any]],
    labels: dict[str, Any],
    methods: Sequence[str],
) -> dict[str, Any]:
    def correct(method: str, iid: str) -> bool:
        ranking = by_id[iid]["methods"][method]["ranking"]
        return bool(ranking) and ranking[0] == labels[iid]["injection_sites"][0]["seq"]

    raw: dict[str, float] = {}
    table: dict[str, Any] = {}
    for a, b in PAIRED:
        if a not in methods or b not in methods:
            continue
        only_a = sum(correct(a, i) and not correct(b, i) for i in ids)
        only_b = sum(correct(b, i) and not correct(a, i) for i in ids)
        name = f"{a}_vs_{b}"
        raw[name] = mcnemar_exact(only_a, only_b)
        table[name] = {"only_first_correct": only_a, "only_second_correct": only_b, "n": len(ids)}
    adjusted = holm(raw)
    for name in table:
        table[name]["p_exact"] = dec(raw[name])
        table[name]["p_holm"] = dec(adjusted[name])
    return {
        "test": "exact two-sided McNemar on Top-1, Holm-adjusted over the listed comparisons",
        "interpretation": "descriptive only; small n, no significance claim is made",
        "comparisons": table,
    }


def _metric_b(
    results: Sequence[dict[str, Any]], labels: dict[str, Any], ids: Sequence[str]
) -> dict[str, Any]:
    causal = [r for r in results if labels[r["instance_id"]]["label"] == "CAUSAL"]
    with_repair = [r for r in causal if r["methods"]["CF"]["repair_sites"]]
    by_id = {r["instance_id"]: r for r in results}
    site_repaired = sum(
        labels[i]["injection_sites"][0]["seq"] in by_id[i]["methods"]["CF"]["repair_sites"]
        for i in ids
    )
    multiple = sorted(
        r["instance_id"] for r in causal if len(r["methods"]["CF"]["repair_sites"]) >= 2
    )
    experiments = [
        s["experiment"]
        for r in results
        for s in r["methods"]["CF"]["steps"]
        if s["experiment"] is not None
    ]
    statuses = Counter(e["status"] for e in experiments)
    placebo_completed = [e for e in experiments if e["placebo_status"] == "COMPLETED"]
    steps = [s for r in results for s in r["methods"]["CF"]["steps"]]
    unsupported = [s for s in steps if s["label"] == "UNSUPPORTED"]
    multi = [
        {
            "instance_id": r["instance_id"],
            "conclusion": r["methods"]["CF"]["conclusion"],
            "repair_sites": r["methods"]["CF"]["repair_sites"],
        }
        for r in causal
        if labels[r["instance_id"]]["kind"] == "MULTI"
    ]
    return {
        "repair_success": proportion(len(with_repair), len(causal)),
        "injected_site_repaired": proportion(site_repaired, len(ids)),
        "multiple_repair_sites": {"count": len(multiple), "instances": multiple},
        "experiments": {
            "total": len(experiments),
            "by_status": dict(sorted(statuses.items())),
            "by_type": dict(sorted(Counter(e["type"] for e in experiments).items())),
        },
        "placebo_validity": proportion(
            sum(e["placebo_valid"] for e in placebo_completed), len(placebo_completed)
        ),
        "placebo_not_completed": len(experiments) - len(placebo_completed),
        "unsupported_steps": proportion(len(unsupported), len(steps)),
        "unsupported_by_reason": dict(
            sorted(Counter(s["note"] or "unspecified" for s in unsupported).items())
        ),
        "multi_fault_cases": multi,
    }


def _metric_c(
    results: Sequence[dict[str, Any]],
    ids: Sequence[str],
    methods: Sequence[str],
    labels: dict[str, Any],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    eligible_set = set(ids)
    causal = [r for r in results if labels[r["instance_id"]]["label"] == "CAUSAL"]
    for method in methods:
        steps = [
            s
            for r in results
            if r["instance_id"] in eligible_set
            for s in r["methods"][method]["steps"]
        ]
        counts = Counter(s["label"] for s in steps)
        conclusions = Counter(r["methods"][method]["conclusion"].split(":")[0] for r in causal)
        out[method] = {
            "step_labels_on_eligible": {label: counts.get(label, 0) for label in LABELS},
            "steps_assessed": len(steps),
            "run_conclusions_on_causal": dict(sorted(conclusions.items())),
        }
    return out


def _checks(
    results: Sequence[dict[str, Any]],
    regressions: Sequence[dict[str, Any]],
    methods: Sequence[str],
    benchmark_problems: Sequence[str],
) -> dict[str, Any]:
    violations: list[str] = []
    replay_ok = sum(r["replay_verdict"] == "VERIFIED" for r in results)
    if replay_ok != len(results):
        violations.append("strict replay not VERIFIED for every recorded instance")
    experiments = [
        s["experiment"]
        for r in results
        for m in methods
        for s in r["methods"][m]["steps"]
        if s["experiment"] is not None
    ]
    completed = [e for e in experiments if e["placebo_status"] == "COMPLETED"]
    invalid = [e for e in completed if not e["placebo_valid"]]
    if invalid:
        violations.append(f"{len(invalid)} completed placebo(s) did not reproduce the original")
    false_repairs = [
        r["instance_id"]
        for r in results
        if r["original_outcome"] == "PASS"
        for m in methods
        if any(s["label"] == "INTERVENTIONAL_REPAIR" for s in r["methods"][m]["steps"])
    ]
    if false_repairs:
        violations.append(f"repair claimed on passing runs: {sorted(set(false_repairs))}")
    silent_unsupported = [
        r["instance_id"]
        for r in results
        for m in methods
        for s in r["methods"][m]["steps"]
        if s["label"] == "UNSUPPORTED" and not s["note"] and "(" not in (s["reference"] or "")
    ]
    if silent_unsupported:
        violations.append(f"UNSUPPORTED steps without a reason: {sorted(set(silent_unsupported))}")
    fence = max((e["cassette_accesses_after_fence"] for e in experiments), default=0)
    if fence:
        violations.append("cassette accessed after the intervention fence")
    regression_cassettes = sum(r["cassettes_constructed"] for r in regressions)
    if regression_cassettes:
        violations.append("regression constructed a cassette")
    status_total = len(experiments)
    if status_total != sum(1 for e in experiments if e["status"]):
        violations.append("experiments with missing status")
    violations.extend(f"benchmark: {p}" for p in benchmark_problems)
    return {
        "strict_replay_verified": proportion(replay_ok, len(results)),
        "placebo_valid_among_completed": proportion(len(completed) - len(invalid), len(completed)),
        "false_repairs_on_passing_runs": len(set(false_repairs)),
        "unsupported_steps_without_reason": len(silent_unsupported),
        "max_cassette_accesses_after_fence": fence,
        "regression_runs_checked": len(regressions),
        "regression_cassettes_constructed": regression_cassettes,
        "benchmark_matches_regeneration": not benchmark_problems,
        "violations": violations,
        "ok": not violations,
    }


def compute_metrics(
    results: Sequence[dict[str, Any]],
    regressions: Sequence[dict[str, Any]],
    labels_list: Sequence[dict[str, Any]],
    *,
    methods: Sequence[str],
    seed: int,
    resamples: int,
    benchmark_problems: Sequence[str] = (),
) -> dict[str, Any]:
    labels = {label["instance_id"]: label for label in labels_list}
    missing = [r["instance_id"] for r in results if r["instance_id"] not in labels]
    if missing:
        raise ValueError(f"no labels for {missing}")
    by_id = {r["instance_id"]: r for r in results}
    ids = eligible(labels, results)
    population = Counter(labels[r["instance_id"]]["label"] for r in results)
    return {
        "population": {
            "instances": len(results),
            "by_label": dict(sorted(population.items())),
            "eligible_for_metric_a": len(ids),
            "eligibility": "label CAUSAL with exactly one injection site (MULTI excluded)",
        },
        "metric_a": {
            "random_reference_B0": _random_reference(ids, by_id),
            "by_method": {
                m: _localization(m, ids, by_id, labels, seed, resamples) for m in methods
            },
            "paired_top1": _paired(ids, by_id, labels, methods),
        },
        "metric_b": _metric_b(results, labels, ids) if "CF" in methods else None,
        "metric_c": _metric_c(results, ids, methods, labels),
        "replay_cost": {
            m: {
                "eligible": summary([by_id[i]["methods"][m]["replays_used"] for i in ids]),
                "all_instances": summary([r["methods"][m]["replays_used"] for r in results]),
            }
            for m in methods
        },
        "regression": list(regressions),
        "checks": _checks(results, regressions, methods, benchmark_problems),
    }
