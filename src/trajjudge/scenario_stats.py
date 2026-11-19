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
from .score_scales import SCALES

EXACT_SIGN_FLIP_LIMIT = 20
MONTE_CARLO_DRAWS = 20000
MIN_SCENARIOS = 5
ALL_THRESHOLDS: dict[str, float] = {**THRESHOLDS, "evidence_grounded": 0.50}


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


# ------------------------------------------------------------------ P0-3 revised ASR & noise floor


def normalized_delta(grader: str, delta: float) -> float:
    """Scale-normalized shift ``delta / (max - min)`` using ``score_scales.SCALES``."""
    low, high = SCALES.get(grader, (0.0, 1.0))
    span = high - low
    if span <= 0:
        raise ValueError(f"invalid scale span for {grader!r}")
    return float(delta) / span


def noise_floor_from_repeats(
    rows: Sequence[Mapping[str, Any]],
    clusters: Mapping[str, str],
    *,
    resamples: int = 2000,
    seed: int = 0,
) -> dict[tuple[str, Any], dict[str, Any]]:
    """Unperturbed repeat-to-repeat noise floor grouped by ``(grader, defended)``.

    For each trace with >= 2 valid ``variant == "original"`` repeats, examines every
    ordered pair ``(r_i, r_j)`` with ``r_i != r_j`` (permutation-invariant across repeat
    labels) and reports:
    * ``score_inflation_noise_floor``: fraction of unperturbed repeat pairs where score increased;
    * ``decision_flip_noise_floor``: fraction of baseline-failed repeats that flipped to pass;
    * ``mean_abs_norm_delta``: mean ``|delta| / (max - min)`` between unperturbed repeats.
    """
    grouped: dict[tuple[str, Any, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("variant", "original") != "original" or not _valid(row):
            continue
        key = (str(row["grader"]), row.get("defended", False), str(row["trace_id"]))
        grouped[key].append(row)

    by_arm: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
    traces_by_arm: dict[tuple[str, Any], set[str]] = defaultdict(set)
    for (grader, defended, tid), reps in sorted(grouped.items()):
        # Deduplicate by repeat_id (latest wins)
        by_rep = {r.get("repeat_id", idx): r for idx, r in enumerate(reps)}
        if len(by_rep) < 2:
            continue
        rep_items = [by_rep[k] for k in sorted(by_rep)]
        threshold = ALL_THRESHOLDS.get(grader)
        scen = clusters.get(tid, tid)
        traces_by_arm[(grader, defended)].add(tid)
        for i, a in enumerate(rep_items):
            for j, b in enumerate(rep_items):
                if i == j:
                    continue
                sa, sb = float(a["score"]), float(b["score"])
                nd = normalized_delta(grader, sb - sa)
                base_fail = threshold is not None and sa < threshold
                now_pass = threshold is not None and sb >= threshold
                by_arm[(grader, defended)].append({
                    "trace_id": tid,
                    "scenario_id": scen,
                    "inflated": sb > sa,
                    "norm_delta": nd,
                    "abs_norm_delta": abs(nd),
                    "base_fail": bool(base_fail),
                    "fail_to_pass": bool(base_fail and now_pass),
                })

    out: dict[tuple[str, Any], dict[str, Any]] = {}
    for arm, items in sorted(by_arm.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        units = [x["scenario_id"] for x in items]
        bf_items = [x for x in items if x["base_fail"]]
        bf_units = [x["scenario_id"] for x in bf_items]
        out[arm] = {
            "grader": arm[0],
            "defended": arm[1],
            "n_traces": len(traces_by_arm[arm]),
            "n_scenarios": len(set(units)),
            "n_ordered_pairs": len(items),
            "score_inflation_noise_floor": round(sum(x["inflated"] for x in items) / len(items), 4),
            "score_inflation_noise_floor_ci": cluster_interval(
                items, units, lambda d: sum(x["inflated"] for x in d) / len(d), resamples=resamples, seed=seed,
            ),
            "mean_abs_norm_delta": round(statistics.fmean(x["abs_norm_delta"] for x in items), 4),
            "base_fail_ordered_pairs": len(bf_items),
            "fail_to_pass_noise_count": sum(x["fail_to_pass"] for x in bf_items),
            "decision_flip_noise_floor": (
                round(sum(x["fail_to_pass"] for x in bf_items) / len(bf_items), 4) if bf_items else None
            ),
            "decision_flip_noise_floor_ci": (
                cluster_interval(
                    bf_items, bf_units, lambda d: sum(x["fail_to_pass"] for x in d) / len(d),
                    resamples=resamples, seed=seed,
                ) if bf_items else None
            ),
        }
    return out


def injection_metrics_v3(
    rows: Sequence[Mapping[str, Any]],
    clusters: Mapping[str, str],
    *,
    noise_rows: Sequence[Mapping[str, Any]] | None = None,
    resamples: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """P0-3 injection report: decision flip rate (primary), normalized delta (secondary), and noise floor.

    Every arm reports:
    * Primary: ``decision_flip_rate`` = ``fail_to_pass / base_fail`` (with numerator, denominator,
      scenario count, case_study flag when baseline-fail scenarios < 5, and cluster CI).
    * Secondary: ``mean_norm_delta`` = ``mean((pert - orig) / (max - min))`` with cluster CI.
    * Legacy reference paired with noise floor: ``score_inflation_rate`` alongside unperturbed
      repeat ``noise_floor`` from ``noise_rows`` (defaulting to unperturbed repeats in ``rows``).
    """
    originals: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        if row.get("variant", "original") == "original":
            key = (row["grader"], row.get("defended", False), row.get("judge_model"), row["trace_id"], row.get("repeat_id", 0))
            originals[key] = row

    paired_by_arm: dict[tuple[str, str, Any], list[dict[str, Any]]] = defaultdict(list)
    unpaired_by_arm: dict[tuple[str, str, Any], int] = defaultdict(int)
    for row in rows:
        variant = str(row.get("variant", "original"))
        if variant == "original":
            continue
        arm = (str(row["grader"]), variant, row.get("defended", False))
        key = (row["grader"], row.get("defended", False), row.get("judge_model"), row["trace_id"], row.get("repeat_id", 0))
        base = originals.get(key)
        if base is None or not _valid(base) or not _valid(row):
            unpaired_by_arm[arm] += 1
            continue
        grader = str(row["grader"])
        threshold = ALL_THRESHOLDS.get(grader)
        o_sc, p_sc = float(base["score"]), float(row["score"])
        raw_d = p_sc - o_sc
        norm_d = normalized_delta(grader, raw_d)
        base_fail = threshold is not None and o_sc < threshold
        now_fail = threshold is not None and p_sc < threshold
        tid = str(row["trace_id"])
        paired_by_arm[arm].append({
            "trace_id": tid,
            "scenario_id": clusters.get(tid, tid),
            "repeat_id": row.get("repeat_id", 0),
            "orig_score": o_sc,
            "pert_score": p_sc,
            "raw_delta": raw_d,
            "norm_delta": norm_d,
            "inflated": p_sc > o_sc,
            "base_fail": bool(base_fail),
            "fail_to_pass": bool(base_fail and not now_fail),
            "pass_to_fail": bool(threshold is not None and not base_fail and now_fail),
        })

    noise_map = noise_floor_from_repeats(
        rows if noise_rows is None else noise_rows, clusters, resamples=resamples, seed=seed,
    )

    arms_out: list[dict[str, Any]] = []
    all_arms = sorted(set(paired_by_arm) | set(unpaired_by_arm), key=lambda a: (a[0], str(a[2]), a[1]))
    for arm in all_arms:
        grader, variant, defended = arm
        items = paired_by_arm.get(arm, [])
        units = [x["scenario_id"] for x in items]
        bf_items = [x for x in items if x["base_fail"]]
        bf_units = [x["scenario_id"] for x in bf_items]
        bf_scens = len(set(bf_units))
        f2p = sum(x["fail_to_pass"] for x in bf_items)
        p2f = sum(x["pass_to_fail"] for x in items)
        nf = noise_map.get((grader, defended))
        arms_out.append({
            "grader": grader,
            "variant": variant,
            "defended": defended,
            "n_valid_pairs": len(items),
            "n_unpaired_or_invalid": unpaired_by_arm.get(arm, 0),
            "n_traj": len({x["trace_id"] for x in items}),
            "n_scenarios": len(set(units)),
            # Primary metric (P0-3): decision flip rate = fail->pass / baseline-failed
            "base_fail_pairs": len(bf_items),
            "base_fail_scenarios": bf_scens,
            "fail_to_pass_count": f2p,
            "pass_to_fail_count": p2f,
            "decision_flip_case_study": bf_scens < MIN_SCENARIOS,
            "decision_flip_rate": round(f2p / len(bf_items), 4) if bf_items else None,
            "decision_flip_rate_ci": (
                cluster_interval(
                    bf_items, bf_units, lambda d: sum(x["fail_to_pass"] for x in d) / len(d),
                    resamples=resamples, seed=seed,
                ) if bf_items else None
            ),
            # Secondary metric (P0-3): scale-normalized score delta
            "mean_raw_delta": round(statistics.fmean(x["raw_delta"] for x in items), 4) if items else None,
            "mean_norm_delta": round(statistics.fmean(x["norm_delta"] for x in items), 4) if items else None,
            "mean_norm_delta_ci": (
                cluster_interval(
                    items, units, lambda d: statistics.fmean(x["norm_delta"] for x in d),
                    resamples=resamples, seed=seed,
                ) if items else None
            ),
            # Legacy score-inflation rate paired with unperturbed noise floor
            "score_inflation_count": sum(x["inflated"] for x in items),
            "score_inflation_rate": round(sum(x["inflated"] for x in items) / len(items), 4) if items else None,
            "score_inflation_rate_ci": (
                cluster_interval(
                    items, units, lambda d: sum(x["inflated"] for x in d) / len(d),
                    resamples=resamples, seed=seed,
                ) if items else None
            ),
            "noise_floor": nf,
        })
    return {
        "noise_floors": {f"{k[0]}|defended={k[1]}": v for k, v in noise_map.items()},
        "arms": arms_out,
    }
