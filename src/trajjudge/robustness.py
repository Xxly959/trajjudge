"""Offline robustness diagnostics for PREREG_v2 §4-§5.

Three things the v1 reports asserted without evidence are recomputed here from
primary artifacts: whether the aggregation strategies really share draws, whether
voting degenerates to min-of-N under the upstream MIN tie-break, and whether
invalid grades are missing at random. Nothing is imputed silently: every
sensitivity arm is labelled and every unrecoverable panel is listed.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from .score_scales import SCALES

DIMENSIONS = ("contribution_score", "relevance_score", "accuracy_score", "efficiency_score")
TAG_RE = re.compile(r"(?P<phase>[^/]+)/(?P<trace>[^/]+)/(?P<variant>[^/]+)/"
                    r"(?P<grader>[^|]+)\|think=(?P<think>on|off)\|(?P<strategy>\w+)/(?P<repeat>\d+)$")
FLOAT_TOL = 1e-9


def draw_score(grader: str, text: str) -> float:
    """Score one raw completion exactly as the upstream grader does.

    The operation order matters: upstream averages each dimension in the raw 1-5
    scale, averages those four, then normalizes once. Reordering changes the last
    bits, and voting compares unrounded floats, so a different order can turn a
    mode into a tie and silently select the minimum instead.
    """
    raw = json.loads(text)
    if grader == "trajectory_accuracy":
        return float(raw["score"])
    steps = raw["step_evaluations"]
    n = len(steps)
    if not n:
        raise ValueError("step_evaluations missing")
    dims = [sum(s[k] for s in steps) / n for k in DIMENSIONS]
    overall = (dims[0] + dims[1] + dims[2] + dims[3]) / 4.0
    return (max(1, min(5, float(overall))) - 1) / 4.0


def mode_min(values: Sequence[float]) -> float:
    """Upstream VotingEvaluationStrategy: modal score, ties resolved to the minimum."""
    counts = Counter(values)
    top = max(counts.values())
    return min(v for v in counts if counts[v] == top)


def parse_tag(tag: str) -> dict[str, Any] | None:
    match = TAG_RE.match(tag or "")
    if not match:
        return None
    parts = match.groupdict()
    return {"phase": parts["phase"], "trace_id": parts["trace"], "variant": parts["variant"],
            "grader": parts["grader"], "thinking": parts["think"] == "on",
            "strategy": parts["strategy"], "repeat_id": int(parts["repeat"])}


def panel_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (row["trace_id"], row.get("variant", "original"), row["grader"],
            row["thinking"], row["repeat_id"], row.get("judge_model"))


def recover_draws(rows: Sequence[Mapping[str, Any]], entries: Sequence[Mapping[str, Any]],
                  *, num_draws: int = 3) -> dict[str, Any]:
    """Recover per-draw scores for shared-draw panels, verifying identity by tokens.

    A panel is accepted only when the cached completions reproduce the recorded
    token totals *and* the recorded aggregate score. Cache tags are not unique per
    request (a rerun can leave two entries under one tag), so token identity, not
    the tag, is the evidence that these are the draws that were actually scored.
    """
    pool: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for entry in entries:
        parts = parse_tag(entry.get("tag", ""))
        if parts is None or parts["strategy"] not in ("direct1", f"average{num_draws}"):
            continue
        key = (parts["trace_id"], parts["variant"], parts["grader"], parts["thinking"],
               parts["repeat_id"], entry.get("model"), entry.get("thinking"))
        pool[key].append(entry)

    panels: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(dict)
    for row in rows:
        panels[panel_key(row)][row.get("strategy", "direct")] = row

    accepted, excluded = [], []
    for key, strategies in sorted(panels.items(), key=lambda item: str(item[0])):
        average = strategies.get("average")
        if average is None:
            continue
        label = {"trace_id": key[0], "variant": key[1], "grader": key[2],
                 "thinking": key[3], "repeat_id": key[4], "judge_model": key[5]}
        candidates = pool.get(key + (average["thinking"],), [])
        if len(candidates) != num_draws:
            excluded.append({**label, "reason": f"expected {num_draws} cached draws, found {len(candidates)}"})
            continue
        usage = average.get("usage") or {}
        if (sum(e["prompt_tokens"] for e in candidates) != usage.get("prompt_tokens")
                or sum(e["completion_tokens"] for e in candidates) != usage.get("completion_tokens")):
            excluded.append({**label, "reason": "cached token totals do not match the recorded row"})
            continue
        if average.get("status") != "ok":
            excluded.append({**label, "reason": "average row is not ok"})
            continue
        try:
            draws = [draw_score(key[2], e["text"]) for e in candidates]
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            excluded.append({**label, "reason": f"raw draw unparseable: {type(exc).__name__}"})
            continue
        if abs(statistics.fmean(draws) - average["score"]) > FLOAT_TOL:
            excluded.append({**label, "reason": "recovered draws do not reproduce the recorded average"})
            continue
        voting = strategies.get("voting")
        voting_check = None
        if voting is not None and voting.get("status") == "ok":
            voting_check = abs(mode_min(draws) - voting["score"]) <= FLOAT_TOL
            if not voting_check:
                excluded.append({**label, "reason": "recovered draws do not reproduce the recorded voting score"})
                continue
        accepted.append({**label, "draws": draws, "average_score": average["score"],
                         "voting_score": None if voting is None else voting.get("score"),
                         "voting_reproduced": voting_check,
                         "voting_api_calls": None if voting is None else (voting.get("usage") or {}).get("api_calls"),
                         "shares_tokens_with_average": voting is not None and (voting.get("usage") or {}).get("prompt_tokens") == usage.get("prompt_tokens")
                         and (voting.get("usage") or {}).get("completion_tokens") == usage.get("completion_tokens")})
    return {"panels": accepted, "excluded": excluded, "panels_seen": len(panels)}


def aggregation_diagnostics(rows: Sequence[Mapping[str, Any]], entries: Sequence[Mapping[str, Any]],
                            *, num_draws: int = 3) -> dict[str, Any]:
    """PREREG_v2 §4: the three shared-draw shares, with recovery coverage stated.

    ``voting < average`` is computable from the rows alone and is therefore reported
    over every ok panel; the draw-level shares are reported only over panels whose
    draws were recovered and verified, so their denominator is never inflated.
    """
    recovered = recover_draws(rows, entries, num_draws=num_draws)
    panels = recovered["panels"]
    by_grader: dict[str, Any] = {}
    for grader in sorted({p["grader"] for p in panels}):
        subset = [p for p in panels if p["grader"] == grader]
        by_grader[grader] = _shares(subset)

    ok_pairs = []
    seen: dict[tuple[Any, ...], dict[str, Any]] = defaultdict(dict)
    for row in rows:
        seen[panel_key(row)][row.get("strategy", "direct")] = row
    for key, strategies in seen.items():
        a, v = strategies.get("average"), strategies.get("voting")
        if a is None or v is None or a.get("status") != "ok" or v.get("status") != "ok":
            continue
        ok_pairs.append({"grader": key[2], "thinking": key[3], "average": a["score"], "voting": v["score"],
                         "shared_tokens": (a.get("usage") or {}).get("prompt_tokens") == (v.get("usage") or {}).get("prompt_tokens")
                         and (a.get("usage") or {}).get("completion_tokens") == (v.get("usage") or {}).get("completion_tokens"),
                         "voting_api_calls": (v.get("usage") or {}).get("api_calls")})
    return {
        "num_draws": num_draws,
        "draw_level": {"panels": len(panels), **_shares(panels), "by_grader": by_grader},
        "row_level": {
            "ok_average_voting_pairs": len(ok_pairs),
            "voting_lt_average": sum(p["voting"] < p["average"] - FLOAT_TOL for p in ok_pairs),
            "voting_lt_average_by_grader": {
                g: {"pairs": sum(p["grader"] == g for p in ok_pairs),
                    "voting_lt_average": sum(p["grader"] == g and p["voting"] < p["average"] - FLOAT_TOL for p in ok_pairs)}
                for g in sorted({p["grader"] for p in ok_pairs})},
            "shared_token_panels": sum(p["shared_tokens"] for p in ok_pairs),
            "voting_zero_new_calls": sum(p["voting_api_calls"] == 0 for p in ok_pairs),
        },
        "recovery": {"panels_seen": recovered["panels_seen"], "verified": len(panels),
                     "excluded": recovered["excluded"],
                     "coverage": len(panels) / recovered["panels_seen"] if recovered["panels_seen"] else None},
        "interpretation": "共享采样的聚合函数对比：voting 与 average 复用同一批抽样，不是独立重复实验",
    }


def _shares(panels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(panels)
    distinct = sum(len(set(p["draws"])) == len(p["draws"]) for p in panels)
    eq_min = sum(abs(p["voting_score"] - min(p["draws"])) <= FLOAT_TOL for p in panels if p["voting_score"] is not None)
    voted = sum(p["voting_score"] is not None for p in panels)
    lt = sum(p["voting_score"] < p["average_score"] - FLOAT_TOL for p in panels if p["voting_score"] is not None)
    return {"panels": n,
            "all_draws_distinct": distinct, "all_draws_distinct_share": distinct / n if n else None,
            "voting_eq_min": eq_min, "voting_eq_min_share": eq_min / voted if voted else None,
            "voting_lt_average": lt, "voting_lt_average_share": lt / voted if voted else None,
            "voting_reproduced": sum(bool(p["voting_reproduced"]) for p in panels)}


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] by summing hypergeometric tails."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1, col1 = a + b, a + c
    lo, hi = max(0, col1 - (n - row1)), min(row1, col1)

    def prob(x: int) -> float:
        return (math.comb(col1, x) * math.comb(n - col1, row1 - x)) / math.comb(n, row1)

    observed = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed * (1 + 1e-9)))


def missingness_report(rows: Sequence[Mapping[str, Any]], *, strata: Sequence[str] = ("defended", "grader", "variant")) -> dict[str, Any]:
    """Invalid-grade rates per stratum plus a defended x invalid exact test.

    The test is exploratory: strata were not pre-registered as hypotheses, and with
    27 invalid rows across 1728 it has little power. It is reported to show whether
    missingness is plausibly random, not to establish that it is not.
    """
    total = len(rows)
    invalid = sum(r.get("status") != "ok" for r in rows)
    out: dict[str, Any] = {"rows": total, "invalid": invalid,
                           "invalid_rate": invalid / total if total else None, "strata": {}}
    for field in strata:
        buckets: dict[Any, list[bool]] = defaultdict(list)
        for r in rows:
            buckets[r.get(field)].append(r.get("status") != "ok")
        out["strata"][field] = [
            {"value": value, "rows": len(flags), "invalid": sum(flags),
             "invalid_rate": sum(flags) / len(flags) if flags else None}
            for value, flags in sorted(buckets.items(), key=lambda item: str(item[0]))]
    if "defended" in strata:
        table = {(bool(r.get("defended", False)), r.get("status") != "ok"): 0 for r in rows}
        for r in rows:
            table[(bool(r.get("defended", False)), r.get("status") != "ok")] += 1
        a = table.get((True, True), 0)
        b = table.get((True, False), 0)
        c = table.get((False, True), 0)
        d = table.get((False, False), 0)
        out["defended_vs_invalid"] = {"table": [[a, b], [c, d]], "fisher_exact_p": fisher_exact_two_sided(a, b, c, d),
                                      "status": "exploratory"}
    return out


def missingness_sensitivity(joined: Sequence[Mapping[str, Any]], grader: str, threshold: float) -> dict[str, Any]:
    """Recompute agreement with invalid grades imputed at each scale extreme.

    ``observed`` drops them (the v1 behaviour). The two imputation arms bound the
    damage: a missing grade treated as the most generous score, then as the least.
    If the conclusion survives both, missingness is not driving it. When nothing is
    missing the arms coincide, which is reported rather than hidden.
    """
    from . import metrics as m

    low, high = SCALES[grader]
    arms: dict[str, Any] = {}
    for name, fill in (("observed", None), ("invalid_as_pass", high), ("invalid_as_fail", low)):
        truth, pred, scores = [], [], []
        for r in joined:
            score = r["scores"].get(grader)
            if score is None:
                if fill is None:
                    continue
                score = fill
            truth.append(bool(r["human"]))
            pred.append(score >= threshold)
            scores.append(score)
        arms[name] = {"n": len(truth), "imputed": sum(r["scores"].get(grader) is None for r in joined) if fill is not None else 0,
                      "accuracy": m.accuracy(truth, pred) if truth else None,
                      "kappa": m.cohen_kappa(truth, pred) if truth else None,
                      "auc": m.auc(truth, scores) if truth else None,
                      "confusion": m.confusion(truth, pred) if truth else None}
    return {"grader": grader, "threshold": threshold, "scale": [low, high], "arms": arms,
            "informative": any(r["scores"].get(grader) is None for r in joined),
            "note": "imputation arms are sensitivity bounds, not estimates of the missing grades"}


def _score_or_fill(row: Mapping[str, Any] | None, fill: float | None) -> float | None:
    if row is None:
        return None
    score = row.get("score")
    if row.get("status") == "ok" and type(score) in (int, float) and math.isfinite(score):
        return float(score)
    return fill


def injection_sensitivity(rows: Sequence[Mapping[str, Any]], grader: str, threshold: float) -> dict[str, Any]:
    """Bound the injection result against the invalid grades it silently dropped.

    Pairs are formed exactly as in ``injection_report``; the only difference is that
    an invalid grade is imputed at a scale extreme instead of excluding the pair.
    Because the defended arm fails to parse more often, this is the check that tells
    us whether the wrapper's apparent benefit is partly a missing-data artifact.
    """
    low, high = SCALES[grader]
    subset = [r for r in rows if r["grader"] == grader]
    originals = {(r["config"], r["trace_id"], r["repeat_id"]): r for r in subset
                 if r.get("variant", "original") == "original"}
    arms: dict[str, Any] = {}
    for name, fill in (("observed", None), ("invalid_as_pass", high), ("invalid_as_fail", low)):
        per_variant: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in subset:
            variant = r.get("variant", "original")
            if variant == "original":
                continue
            base = originals.get((r["config"], r["trace_id"], r["repeat_id"]))
            if base is None:
                per_variant[variant]["unpaired"] += 1
                continue
            b = _score_or_fill(base, fill)
            v = _score_or_fill(r, fill)
            if b is None or v is None:
                per_variant[variant]["excluded"] += 1
                continue
            bucket = per_variant[variant]
            bucket["pairs"] += 1
            bucket["positive"] += v > b
            bucket["base_fail"] += b < threshold
            bucket["fail_to_pass"] += b < threshold <= v
            bucket["pass_to_fail"] += v < threshold <= b
            bucket["verdict_changed"] += (b < threshold) != (v < threshold)
            bucket["imputed"] += (base.get("status") != "ok") + (r.get("status") != "ok")
        totals = {k: sum(b[k] for b in per_variant.values()) for k in
                  ("pairs", "positive", "base_fail", "fail_to_pass", "pass_to_fail", "verdict_changed", "imputed", "excluded", "unpaired")}
        arms[name] = {**totals,
                      "asr": totals["positive"] / totals["pairs"] if totals["pairs"] else None,
                      "verdict_flip_rate": totals["verdict_changed"] / totals["pairs"] if totals["pairs"] else None,
                      "per_variant": {k: dict(v) for k, v in sorted(per_variant.items())}}
    return {"grader": grader, "threshold": threshold, "scale": [low, high], "arms": arms,
            "note": "observed excludes invalid pairs; the imputation arms bound their influence"}