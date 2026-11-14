"""Scenario-level injection statistics frozen in PREREG_v2 §6/§6b.

The unit of analysis is the independent scenario, not the trajectory: translation
copies of one task are pseudo-replicates and must travel together. Every rate here
is a count of scenarios over a count of scenarios, and the permutation test flips
signs per scenario rather than per observation.
"""

from __future__ import annotations

import itertools
import random
import statistics
from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence

from . import metrics as m
from .analysis import _group, _valid, cluster_interval
from .agreement import THRESHOLDS

EXACT_SIGN_FLIP_LIMIT = 20
MONTE_CARLO_DRAWS = 20000
MIN_SCENARIOS = 5


def paired_observations(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Baseline/perturbed pairs under the same validity rule as ``injection_report``.

    An invalid or missing baseline is dropped from the pair, never imputed; the
    caller reports the dropped count so coverage stays visible.
    """
    originals = {(_group(r), r["trace_id"], r["repeat_id"]): r
                 for r in rows if r.get("variant", "original") == "original"}
    pairs: list[dict[str, Any]] = []
    unpaired = 0
    for row in rows:
        variant = row.get("variant", "original")
        if variant == "original":
            continue
        base = originals.get((_group(row), row["trace_id"], row["repeat_id"]))
        if base is None or not _valid(base) or not _valid(row):
            unpaired += 1
            continue
        threshold = THRESHOLDS.get(row["grader"])
        base_fail = threshold is not None and base["score"] < threshold
        now_fail = threshold is not None and row["score"] < threshold
        pairs.append({"config": row["config"], "grader": row["grader"], "variant": variant,
                      "defended": bool(row.get("defended", False)), "trace_id": row["trace_id"],
                      "repeat_id": row["repeat_id"], "delta": row["score"] - base["score"],
                      "base_fail": bool(base_fail),
                      "fail_to_pass": bool(base_fail and not now_fail),
                      "pass_to_fail": bool(threshold is not None and not base_fail and now_fail),
                      "verdict_changed": bool(threshold is not None and base_fail != now_fail)})
    return pairs, unpaired


def cells(pairs: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, bool], list[dict[str, Any]]]:
    """Group pairs into (grader, variant, defended) units; the defense arms stay separate."""
    out: dict[tuple[str, str, bool], list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        out[(pair["grader"], pair["variant"], pair["defended"])].append(pair)
    return dict(out)


def scenario_aggregates(pairs: Sequence[Mapping[str, Any]], clusters: Mapping[str, str]) -> list[dict[str, Any]]:
    """One record per scenario holding every pair of that scenario, so resampling keeps twins together."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for pair in pairs:
        grouped[clusters[pair["trace_id"]]].append(pair)
    out = []
    for scenario, group in sorted(grouped.items()):
        mean = statistics.fmean(p["delta"] for p in group)
        out.append({
            "scenario_id": scenario,
            "traces": sorted({p["trace_id"] for p in group}),
            "pairs": len(group),
            "mean_delta": mean,
            "positive": sum(p["delta"] > 0 for p in group),
            "base_fail": sum(p["base_fail"] for p in group),
            "fail_to_pass": sum(p["fail_to_pass"] for p in group),
            "pass_to_fail": sum(p["pass_to_fail"] for p in group),
            "verdict_changed": sum(p["verdict_changed"] for p in group),
            "asr_flip": mean > 0,
            "asr_any": any(p["delta"] > 0 for p in group),
            "verdict_flip": any(p["verdict_changed"] for p in group),
            "f2p_flip": sum(p["fail_to_pass"] for p in group) > sum(p["pass_to_fail"] for p in group),
            "p2f_flip": sum(p["pass_to_fail"] for p in group) > sum(p["fail_to_pass"] for p in group),
        })
    return out


FLIP_METRICS = ("asr_flip", "verdict_flip", "f2p_flip", "p2f_flip", "asr_any")


def scenario_rates(aggregates: Sequence[Mapping[str, Any]], *, resamples: int = 2000,
                   seed: int = 0) -> dict[str, Any]:
    """Scenarios flipped / scenarios with a valid pair, with the §2 interval rules."""
    items = list(aggregates)
    n = len(items)
    total_pairs = sum(a["pairs"] for a in items)
    out: dict[str, Any] = {
        "n_scenario": n,
        "n_traj": len({t for a in items for t in a["traces"]}),
        "pairs": total_pairs,
        "case_study": n < MIN_SCENARIOS,
        "informative_clusters": sum(a["mean_delta"] != 0 for a in items),
        "counts": {name: sum(bool(a[name]) for a in items) for name in FLIP_METRICS},
        "pair_level": {
            "positive": sum(a["positive"] for a in items),
            "asr": sum(a["positive"] for a in items) / total_pairs if total_pairs else None,
            "base_fail": sum(a["base_fail"] for a in items),
            "fail_to_pass": sum(a["fail_to_pass"] for a in items),
            "pass_to_fail": sum(a["pass_to_fail"] for a in items),
            "verdict_changed": sum(a["verdict_changed"] for a in items),
            "verdict_flip_rate": sum(a["verdict_changed"] for a in items) / total_pairs if total_pairs else None,
        },
        "rates": {}, "intervals": {},
    }
    for name in FLIP_METRICS:
        stat: Callable[[Sequence[Any]], float | None] = lambda data, key=name: (
            sum(bool(a[key]) for a in data) / len(data) if data else None)
        out["rates"][name] = stat(items)
        out["intervals"][name] = cluster_interval(items, [a["scenario_id"] for a in items], stat,
                                                  resamples=resamples, seed=seed)
        if out["case_study"]:
            out["rates"][name] = None
    return out


def sign_flip_test(cluster_means: Sequence[float], *, seed: int = 0) -> dict[str, Any]:
    """Exact cluster-level sign-flip test of H1: mean paired shift > 0 (PREREG_v2 §6b).

    Every scenario's whole block of pairs takes one sign, so translation copies
    cannot manufacture significance by being counted as independent draws.
    """
    means = [float(x) for x in cluster_means]
    k = len(means)
    if not k:
        return {"status": "not_estimable", "k": 0, "statistic": None, "p": None,
                "nonzero_clusters": 0, "reason": m.NOT_ESTIMABLE, "exact": True}
    observed = statistics.fmean(means)
    if k <= EXACT_SIGN_FLIP_LIMIT:
        assignments = itertools.product((1, -1), repeat=k)
        total = 2 ** k
        exact = True
    else:
        rng = random.Random(seed)
        assignments = ([rng.choice((1, -1)) for _ in range(k)] for _ in range(MONTE_CARLO_DRAWS))
        total = MONTE_CARLO_DRAWS + 1
        exact = False
    # The observed assignment counts toward the p-value; Monte Carlo must add it
    # explicitly, otherwise a strong effect can report the impossible p = 0.
    hits = 0 if exact else 1
    for signs in assignments:
        value = statistics.fmean(s * x for s, x in zip(signs, means, strict=True))
        if value >= observed - 1e-12:
            hits += 1
    return {"status": "ok", "k": k, "statistic": observed, "p": hits / total,
            "nonzero_clusters": sum(x != 0 for x in means),
            "assignments": total, "exact": exact, "alternative": "greater",
            "reason": None if exact else f"Monte Carlo with {MONTE_CARLO_DRAWS} draws plus the observed assignment, seed {seed}"}


def holm(tests: Mapping[str, float | None], *, alpha: float = 0.05) -> dict[str, Any]:
    """Holm step-down FWER control over the tests that could actually be computed.

    A unit with too few contributing scenarios has no p-value and is reported as
    descriptive; it is not silently counted as a non-significant member of the family.
    """
    computed = {name: p for name, p in tests.items() if p is not None}
    skipped = sorted(name for name, p in tests.items() if p is None)
    order = sorted(computed, key=lambda name: (computed[name], name))
    total = len(order)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, name in enumerate(order):
        running = max(running, (total - rank) * computed[name])
        adjusted[name] = min(1.0, running)
    return {
        "method": "holm", "alpha": alpha, "family_size": total, "skipped": skipped,
        "tests": {name: {"p": computed[name], "p_adjusted": adjusted[name],
                         "reject": adjusted[name] <= alpha} for name in order},
        "rejected": sorted(name for name in order if adjusted[name] <= alpha),
    }


def scenario_table(aggregates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per-scenario counts, so a rate can always be traced back to the evidence behind it."""
    return [{key: a[key] for key in ("scenario_id", "traces", "pairs", "mean_delta", "positive",
                                     "base_fail", "fail_to_pass", "pass_to_fail", "verdict_changed",
                                     "asr_flip", "verdict_flip")} for a in aggregates]