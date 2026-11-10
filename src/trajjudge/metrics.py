"""Pure-Python agreement and stability metrics with seeded bootstrap intervals."""

from __future__ import annotations

import itertools
import math
import random
import statistics
from collections import Counter
from typing import Callable, Mapping, Sequence


def accuracy(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Fraction of positions where the two label sequences agree."""
    if len(a) != len(b) or not a:
        raise ValueError("sequences must be non-empty and equal length")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def confusion(truth: Sequence[bool], pred: Sequence[bool]) -> dict[str, int]:
    """Binary confusion counts; positive = pass."""
    pairs = list(zip(truth, pred))
    return {"tp": sum(t and p for t, p in pairs), "fp": sum((not t) and p for t, p in pairs),
            "fn": sum(t and (not p) for t, p in pairs), "tn": sum((not t) and (not p) for t, p in pairs)}


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    """Cohen's kappa for two binary raters; ``None`` when chance agreement is 1 (undefined)."""
    n = len(a)
    if n == 0 or n != len(b):
        raise ValueError("sequences must be non-empty and equal length")
    observed = accuracy(a, b)
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    return None if math.isclose(expected, 1.0) else (observed - expected) / (1 - expected)


def pabak(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Prevalence-adjusted bias-adjusted kappa: 2 * accuracy - 1 (robust to skewed labels)."""
    return 2 * accuracy(a, b) - 1


def bootstrap_ci(stat: Callable[[Sequence[int]], float | None], n: int, *, resamples: int = 2000, seed: int = 0,
                 level: float = 0.95) -> tuple[float, float] | None:
    """Percentile bootstrap CI of ``stat(indices)`` over ``n`` items; undefined resamples are dropped.

    Returns ``None`` if fewer than half of the resamples produced a value.
    """
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        value = stat([rng.randrange(n) for _ in range(n)])
        if value is not None:
            values.append(value)
    if len(values) < resamples / 2:
        return None
    values.sort()
    lo = values[int((1 - level) / 2 * (len(values) - 1))]
    hi = values[int((1 + level) / 2 * (len(values) - 1))]
    return lo, hi


def baselines(truth: Sequence[bool], *, seed: int = 0) -> dict[str, float]:
    """Accuracy of trivial predictors against ``truth``: always-pass, majority class, random 50/50 (expected)."""
    n = len(truth)
    rng = random.Random(seed)
    rand = statistics.fmean(accuracy(truth, [rng.random() < 0.5 for _ in truth]) for _ in range(1000))
    return {"always_pass": sum(truth) / n, "majority": max(sum(truth), n - sum(truth)) / n,
            "random": rand}


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties; ``None`` if either side is constant."""
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("need two equal-length sequences with at least 2 items")
    rx, ry = _ranks(x), _ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if sx == 0 or sy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy)


def stability_summary(scores: Mapping[str, Sequence[float]], threshold: float) -> dict[str, float | int | None]:
    """Repeat-stability of scores per trace.

    Args:
        scores: trace_id -> scores from repeated runs (same config, ``>= 2`` repeats each).
        threshold: ``score >= threshold`` counts as pass.

    Returns mean per-trace SD (ddof=1), flip rate (share of traces whose repeats disagree on
    pass/fail), pairwise decision disagreement, and mean pairwise Spearman / kappa across repeat indices.
    """
    usable = {k: list(v) for k, v in scores.items() if len(v) >= 2}
    if not usable:
        raise ValueError("no trace has two or more repeats")
    reps = min(len(v) for v in usable.values())
    ids = sorted(usable)
    sds = [statistics.stdev(usable[t]) for t in ids]
    flips = [len({s >= threshold for s in usable[t]}) > 1 for t in ids]
    pair_dis = [statistics.fmean((usable[t][i] >= threshold) != (usable[t][j] >= threshold) for t in ids)
                for i, j in itertools.combinations(range(reps), 2)]
    rhos, kappas = [], []
    for i, j in itertools.combinations(range(reps), 2):
        xs, ys = [usable[t][i] for t in ids], [usable[t][j] for t in ids]
        rho = spearman(xs, ys) if len(ids) >= 2 else None
        kap = cohen_kappa([v >= threshold for v in xs], [v >= threshold for v in ys])
        if rho is not None:
            rhos.append(rho)
        if kap is not None:
            kappas.append(kap)
    return {"traces": len(ids), "repeats": reps, "mean_sd": statistics.fmean(sds), "flip_rate": sum(flips) / len(flips),
            "pairwise_disagreement": statistics.fmean(pair_dis),
            "mean_spearman": statistics.fmean(rhos) if rhos else None,
            "mean_kappa": statistics.fmean(kappas) if kappas else None}


def label_counts(labels: Sequence[bool]) -> dict[str, int]:
    """Class balance report (kappa becomes unstable when one class is rare)."""
    c = Counter(labels)
    return {"pass": c[True], "fail": c[False]}


def auc(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """Probability a random positive outscores a random negative (ties count half); ``None`` if one class is absent."""
    pos = [s for l, s in zip(labels, scores) if l]
    neg = [s for l, s in zip(labels, scores) if not l]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))
