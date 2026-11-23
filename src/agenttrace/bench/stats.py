"""Small, dependency-free statistics for benchmark reporting (docs/EVALUATION.md).

- Wilson 95% score interval for proportions.
- Percentile bootstrap, resampling *templates* (clusters) with replacement, fixed seed.
- Exact two-sided McNemar test (binomial on discordant pairs) with Holm correction.

Rates are converted to 4-decimal ``Decimal`` values before serialization, so canonical JSON
stays float-free and byte-stable.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal

from agenttrace.replay.regression import wilson_interval

_Q = Decimal("0.0001")


def dec(value: float) -> Decimal:
    return Decimal(repr(value)).quantize(_Q, rounding=ROUND_HALF_EVEN)


def proportion(k: int, n: int) -> dict[str, object]:
    """``{"k", "n", "rate", "ci95"}``; rate and CI are null when n == 0."""
    if n == 0:
        return {"k": k, "n": n, "rate": None, "ci95": None}
    low, high = wilson_interval(k, n)
    return {"k": k, "n": n, "rate": dec(k / n), "ci95": [dec(low), dec(high)]}


def cluster_bootstrap_mean(
    values: Sequence[float],
    clusters: Sequence[str],
    *,
    seed: int = 0,
    resamples: int = 2000,
) -> tuple[Decimal, Decimal] | None:
    """95% percentile interval of the mean, resampling clusters (templates) with replacement."""
    if not values:
        return None
    by_cluster: dict[str, list[float]] = {}
    for value, cluster in zip(values, clusters, strict=True):
        by_cluster.setdefault(cluster, []).append(value)
    keys = sorted(by_cluster)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        pooled: list[float] = []
        for _k in keys:
            pooled.extend(by_cluster[rng.choice(keys)])
        means.append(sum(pooled) / len(pooled))
    means.sort()
    low = means[int(0.025 * (resamples - 1))]
    high = means[math.ceil(0.975 * (resamples - 1))]
    return dec(low), dec(high)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from discordant counts b (A right, B wrong) and c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = float(sum(math.comb(n, i) for i in range(min(b, c) + 1))) / float(2**n)
    return min(1.0, 2.0 * tail)


def holm(pvalues: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (monotone)."""
    ordered = sorted(pvalues.items(), key=lambda kv: (kv[1], kv[0]))
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for index, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - index) * p))
        adjusted[name] = running
    return adjusted


def summary(values: Sequence[int]) -> dict[str, object]:
    """Mean / median / max / total of non-negative integers (e.g. replays per investigation)."""
    if not values:
        return {"n": 0, "mean": None, "median": None, "max": None, "total": 0}
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "n": len(values),
        "mean": dec(sum(values) / len(values)),
        "median": dec(float(median)),
        "max": max(values),
        "total": sum(values),
    }
