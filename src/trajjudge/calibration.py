"""Leave-one-scenario-out threshold calibration frozen in PREREG_v2 §7/§7b.

A threshold chosen on the same labels it is then scored against is not a
calibration, it is a fit. Every fold here holds out a whole scenario, selects on
the remaining scenarios only, and predicts on the held-out one; the reported
metrics come from pooling those out-of-fold predictions. Translation twins stay
in the same fold so a zh/en pair cannot leak across the train/test boundary.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence

from . import metrics as m
from .agreement import THRESHOLDS
from .analysis import cluster_interval

GRIDS: dict[str, tuple[float, ...]] = {
    "trajectory_accuracy": (1.0, 1.5, 2.0, 2.5, 3.0),
    "trajectory_comprehensive": tuple(round(0.50 + 0.05 * i, 2) for i in range(11)),
}
SENTINELS = ("always_pass", "always_fail")
MISS_RATES = (0.10, 0.25, 0.50)
PRIMARY_MISS_RATE = 0.25
MIN_SCENARIOS = 5


def candidates(grader: str) -> list[dict[str, Any]]:
    """Grid points then sentinels, in the frozen tie-break order (smaller value first)."""
    if grader not in GRIDS:
        raise ValueError(f"no frozen threshold grid for {grader!r}")
    default = THRESHOLDS[grader]
    out = [{"kind": "threshold", "value": v, "distance": abs(v - default)} for v in GRIDS[grader]]
    out += [{"kind": name, "value": None, "distance": math.inf} for name in SENTINELS]
    return out


def predict(score: float, choice: Mapping[str, Any]) -> bool:
    if choice["kind"] == "always_pass":
        return True
    if choice["kind"] == "always_fail":
        return False
    return score >= choice["value"]


def describe(choice: Mapping[str, Any]) -> str:
    return choice["kind"] if choice["value"] is None else f"{choice['kind']}:{choice['value']}"


def binary_metrics(truth: Sequence[bool], pred: Sequence[bool]) -> dict[str, Any]:
    """Confusion plus the rates that need a class to exist; undefined stays ``None``.

    Positive = pass, so a human fail judged pass is a false positive and the miss
    rate is ``fp / (fp + tn)``. Returning 0.0 for an empty class would invent a
    perfect score out of no evidence.
    """
    c = m.confusion(truth, pred)
    n_pass, n_fail = c["tp"] + c["fn"], c["tn"] + c["fp"]
    sensitivity = c["tp"] / n_pass if n_pass else None
    specificity = c["tn"] / n_fail if n_fail else None
    balanced = (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None
    return {"n": len(truth), "confusion": c, "n_human_pass": n_pass, "n_human_fail": n_fail,
            "sensitivity": sensitivity, "specificity": specificity, "balanced_accuracy": balanced,
            "miss_rate": c["fp"] / n_fail if n_fail else None,
            "accuracy": m.accuracy(truth, pred) if truth else None,
            "kappa": m.cohen_kappa(truth, pred) if truth else None,
            "pabak": m.pabak(truth, pred) if truth else None}


def _train_pairs(rows: Sequence[Mapping[str, Any]], grader: str,
                 choice: Mapping[str, Any]) -> tuple[list[bool], list[bool]]:
    usable = [r for r in rows if r["scores"].get(grader) is not None]
    return ([bool(r["human"]) for r in usable],
            [predict(r["scores"][grader], choice) for r in usable])


def select(rows: Sequence[Mapping[str, Any]], grader: str, *,
           target_miss: float | None = None) -> dict[str, Any]:
    """Pick a threshold on training rows only.

    ``target_miss=None`` maximizes balanced accuracy; otherwise it takes the
    grid point whose training miss rate is closest to the target from below.
    Ties go to the value nearer the upstream default, then to the smaller value.
    """
    pool = candidates(grader)
    scored = []
    for position, choice in enumerate(pool):
        truth, pred = _train_pairs(rows, grader, choice)
        stats = binary_metrics(truth, pred)
        objective = stats["balanced_accuracy"] if target_miss is None else stats["miss_rate"]
        scored.append({"position": position, "choice": choice, "stats": stats, "objective": objective})
    defined = [s for s in scored if s["objective"] is not None]
    if not defined:
        return {"choice": None, "undefined": True, "target_miss": target_miss,
                "reason": "训练折缺少某一类，目标未定义", "train_n": len(rows),
                "considered": [{"threshold": describe(s["choice"]), "objective": s["objective"]} for s in scored]}
    if target_miss is None:
        best = min(defined, key=lambda s: (-s["objective"], s["choice"]["distance"], s["position"]))
    else:
        feasible = [s for s in defined if s["objective"] <= target_miss + 1e-12]
        if not feasible:
            return {"choice": None, "undefined": True, "target_miss": target_miss,
                    "reason": f"没有网格点的训练漏判率 ≤ {target_miss}", "train_n": len(rows),
                    "considered": [{"threshold": describe(s["choice"]), "objective": s["objective"]} for s in scored]}
        best = min(feasible, key=lambda s: (abs(s["objective"] - target_miss), s["choice"]["distance"], s["position"]))
    return {"choice": best["choice"], "undefined": False, "target_miss": target_miss,
            "threshold": describe(best["choice"]), "train_n": len(rows),
            "train_metrics": best["stats"], "objective_value": best["objective"],
            "considered": [{"threshold": describe(s["choice"]), "objective": s["objective"]} for s in scored]}


def fold_plan(rows: Sequence[Mapping[str, Any]], clusters: Mapping[str, str]) -> list[dict[str, Any]]:
    """One fold per scenario, holding out the entire cluster."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[clusters[row["trace_id"]]].append(row)
    plan = []
    for scenario in sorted(grouped):
        plan.append({"scenario_id": scenario, "test": grouped[scenario],
                     "train": [r for s, group in grouped.items() if s != scenario for r in group]})
    return plan


def out_of_fold(plan: Sequence[Mapping[str, Any]], grader: str, *,
                target_miss: float | None = None) -> dict[str, Any]:
    """Predict each held-out scenario with a threshold chosen without it."""
    oof: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []
    for fold in plan:
        chosen = select(fold["train"], grader, target_miss=target_miss)
        fallback = chosen["undefined"]
        choice = chosen["choice"] or {"kind": "threshold", "value": THRESHOLDS[grader], "distance": 0.0}
        entry = {"scenario_id": fold["scenario_id"], "n_train": len(fold["train"]),
                 "n_test": len(fold["test"]), "threshold": describe(choice),
                 "fallback": fallback, "reason": chosen.get("reason"),
                 "train_metrics": chosen.get("train_metrics")}
        folds.append(entry)
        for row in fold["test"]:
            score = row["scores"].get(grader)
            if score is None:
                continue
            oof.append({"trace_id": row["trace_id"], "task_id": row["task_id"],
                        "scenario_id": fold["scenario_id"], "human": bool(row["human"]),
                        "official": bool(row["official"]), "score": score,
                        "pred": predict(score, choice), "threshold": describe(choice),
                        "fallback": fallback})
    return {"grader": grader, "target_miss": target_miss, "oof": oof, "folds": folds,
            "n_folds": len(folds), "undefined_folds": sum(f["fallback"] for f in folds),
            "fallback_folds": [f["scenario_id"] for f in folds if f["fallback"]],
            "undefined_share": sum(f["fallback"] for f in folds) / len(folds) if folds else None}


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """PR-AUC as step-interpolated average precision; ``None`` when a class is absent."""
    if len(labels) != len(scores):
        raise ValueError("labels and scores must be the same length")
    positives = sum(labels)
    if not positives or positives == len(labels):
        return None
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    ap, recall_prev, tp, seen = 0.0, 0.0, 0, 0
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and scores[order[end + 1]] == scores[order[index]]:
            end += 1
        for i in order[index:end + 1]:
            tp += bool(labels[i])
        seen += end - index + 1
        recall = tp / positives
        ap += (recall - recall_prev) * (tp / seen)
        recall_prev = recall
        index = end + 1
    return ap


def _interval(rows: Sequence[Mapping[str, Any]], stat: Callable[[Sequence[Any]], float | None],
              *, resamples: int, seed: int, contributing: int | None = None) -> dict[str, Any]:
    return cluster_interval(list(rows), [r["scenario_id"] for r in rows], stat,
                            resamples=resamples, seed=seed, contributing=contributing)


def summarize(oof: Sequence[Mapping[str, Any]], *, resamples: int = 2000, seed: int = 0) -> dict[str, Any]:
    """Out-of-fold metrics with scenario-cluster intervals, per PREREG_v2 §2/§7b."""
    rows = sorted(oof, key=lambda r: (r["scenario_id"], r["trace_id"]))
    n = len(rows)
    if not n:
        return {"n": 0, "status": "not_estimable", "reason": m.NOT_ESTIMABLE}
    truth = [bool(r["human"]) for r in rows]
    pred = [bool(r["pred"]) for r in rows]
    scores = [float(r["score"]) for r in rows]
    base = binary_metrics(truth, pred)
    clusters = sorted({r["scenario_id"] for r in rows})
    contributing = len({r["scenario_id"] for r in rows if r["score"] is not None})
    out: dict[str, Any] = {
        "n": n, "n_scenario": len(clusters), "n_traj": len({r["trace_id"] for r in rows}),
        "case_study": len(clusters) < MIN_SCENARIOS, "labels": m.label_counts(truth),
        **base,
        "auc_pass": m.auc(truth, scores),
        "pr_auc_fail": average_precision([not t for t in truth], [-s for s in scores]),
        "baselines": m.baselines(truth, seed=seed),
        "fallback_rows": sum(bool(r["fallback"]) for r in rows),
        "intervals": {},
    }
    out["auc_fail"] = None if out["auc_pass"] is None else 1.0 - out["auc_pass"]
    stats: dict[str, Callable[[Sequence[Any]], float | None]] = {
        "accuracy": lambda d: m.accuracy([r["human"] for r in d], [r["pred"] for r in d]) if d else None,
        "kappa": lambda d: m.cohen_kappa([r["human"] for r in d], [r["pred"] for r in d]) if d else None,
        "pabak": lambda d: m.pabak([r["human"] for r in d], [r["pred"] for r in d]) if d else None,
        "balanced_accuracy": lambda d: binary_metrics([r["human"] for r in d], [r["pred"] for r in d])["balanced_accuracy"] if d else None,
        "sensitivity": lambda d: binary_metrics([r["human"] for r in d], [r["pred"] for r in d])["sensitivity"] if d else None,
        "specificity": lambda d: binary_metrics([r["human"] for r in d], [r["pred"] for r in d])["specificity"] if d else None,
        "miss_rate": lambda d: binary_metrics([r["human"] for r in d], [r["pred"] for r in d])["miss_rate"] if d else None,
        "auc_pass": lambda d: m.auc([r["human"] for r in d], [r["score"] for r in d]) if d else None,
        "pr_auc_fail": lambda d: average_precision([not r["human"] for r in d], [-r["score"] for r in d]) if d else None,
    }
    for name, stat in stats.items():
        out["intervals"][name] = _interval(rows, stat, resamples=resamples, seed=seed, contributing=contributing)
    # Every constant predictor has balanced accuracy 0.5 when both classes exist,
    # and a 50/50 random one has 0.5 in expectation, so the baselines are computed
    # from that identity rather than from one arbitrary random draw.
    out["baseline_balanced"] = {name: 0.5 if base["n_human_pass"] and base["n_human_fail"] else None
                                for name in ("always_pass", "majority", "random")}
    out["auc_covers_half"] = _covers_half(out["intervals"]["auc_pass"])
    out["no_usable_discrimination"] = out["auc_covers_half"] is True
    return out


def _covers_half(interval: Mapping[str, Any]) -> bool | None:
    ci = interval.get("ci")
    if not ci:
        return None
    return bool(ci[0] <= 0.5 <= ci[1])


def hard_samples(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PREREG_v2 §7: human fail that the framework and both graders all passed."""
    out = []
    for row in rows:
        scores = row["scores"]
        if row["human"] or not row["official"]:
            continue
        if any(scores.get(g) is None or scores[g] < THRESHOLDS[g] for g in THRESHOLDS):
            continue
        out.append(row)
    return out


def hybrid_evidence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Do executable checks and LLM judges miss different human failures?

    Reported as counts, never as a recommendation: with a handful of scenarios the
    union can look better by chance, so the caller must apply the §7b rule.
    """
    fails = [r for r in rows if not r["human"]]
    passes = [r for r in rows if r["human"]]

    def missed(row: Mapping[str, Any], grader: str) -> bool:
        """A human failure this grader did not flag; a missing grade is not a catch."""
        score = row["scores"].get(grader)
        return score is None or score >= THRESHOLDS[grader]

    def false_kill(row: Mapping[str, Any], grader: str) -> bool:
        """A human pass this grader flagged as fail; a missing grade is not a kill."""
        score = row["scores"].get(grader)
        return score is not None and score < THRESHOLDS[grader]

    caught = {"framework": [r for r in fails if not r["official"]],
              **{g: [r for r in fails if not missed(r, g)] for g in THRESHOLDS}}
    union = [r for r in fails if not r["official"] or any(not missed(r, g) for g in THRESHOLDS)]
    framework_only = [r for r in caught["framework"] if all(missed(r, g) for g in THRESHOLDS)]
    graders_only = [r for r in fails if r["official"] and any(not missed(r, g) for g in THRESHOLDS)]
    neither = [r for r in fails if r["official"] and all(missed(r, g) for g in THRESHOLDS)]
    both = [r for r in caught["framework"] if any(not missed(r, g) for g in THRESHOLDS)]
    return {
        "n_human_fail": len(fails), "n_human_pass": len(passes),
        "n_scenario_fail": len({r.get("scenario_id") or r["task_id"] for r in fails}),
        "caught_by": {name: len(group) for name, group in caught.items()},
        "caught_union": len(union),
        "miss_rate": {name: 1 - len(group) / len(fails) if fails else None for name, group in caught.items()},
        "miss_rate_union": 1 - len(union) / len(fails) if fails else None,
        "framework_only": sorted(r["trace_id"] for r in framework_only),
        "graders_only": sorted(r["trace_id"] for r in graders_only),
        "neither": sorted(r["trace_id"] for r in neither),
        "both": sorted(r["trace_id"] for r in both),
        # A false kill is a human pass judged fail. Counting agreement here would
        # invert the evidence for/against a hybrid scorer.
        "framework_false_fail_on_human_pass": sum(not r["official"] for r in passes),
        "grader_false_fail_on_human_pass": {g: sum(false_kill(r, g) for r in passes) for g in THRESHOLDS},
        "status": "exploratory",
    }


# ------------------------------------------------------------------ P0-4 same-FPR & McNemar


def roc_curve_fail(truth_pass: Sequence[bool], scores: Sequence[float]) -> list[dict[str, float | None]]:
    """ROC curve for failure detection (positive = fail, higher failure signal = lower score).

    Returns monotonically non-decreasing ``(fpr, tpr)`` points from ``(0, 0)`` to ``(1, 1)``,
    where ``fpr`` is the false-kill rate on true passes and ``tpr`` is failure recall on true fails.
    Ties in score are stepped together so tie ordering never manufactures optimistic points.
    """
    if len(truth_pass) != len(scores):
        raise ValueError("truth_pass and scores must be the same length")
    n_fail = sum(not t for t in truth_pass)
    n_pass = sum(bool(t) for t in truth_pass)
    if not n_fail or not n_pass:
        return []
    # Predict fail when score <= cutoff (ascending score order).
    order = sorted(range(len(scores)), key=lambda i: float(scores[i]))
    points: list[dict[str, float | None]] = [{"fpr": 0.0, "tpr": 0.0, "threshold": None}]
    tp_fail = 0
    fp_kill = 0
    idx = 0
    while idx < len(order):
        end = idx
        cutoff = float(scores[order[idx]])
        while end + 1 < len(order) and float(scores[order[end + 1]]) == cutoff:
            end += 1
        for pos in order[idx : end + 1]:
            if truth_pass[pos]:
                fp_kill += 1
            else:
                tp_fail += 1
        points.append({
            "fpr": fp_kill / n_pass,
            "tpr": tp_fail / n_fail,
            "threshold": cutoff,
        })
        idx = end + 1
    return points


def pr_curve_fail(truth_pass: Sequence[bool], scores: Sequence[float]) -> list[dict[str, float | None]]:
    """Precision-Recall curve for failure detection (positive = fail, ascending score cutoff)."""
    if len(truth_pass) != len(scores):
        raise ValueError("truth_pass and scores must be the same length")
    n_fail = sum(not t for t in truth_pass)
    n_pass = sum(bool(t) for t in truth_pass)
    if not n_fail or not n_pass:
        return []
    order = sorted(range(len(scores)), key=lambda i: float(scores[i]))
    points: list[dict[str, float | None]] = [{"recall": 0.0, "precision": 1.0, "threshold": None}]
    tp_fail = 0
    seen = 0
    idx = 0
    while idx < len(order):
        end = idx
        cutoff = float(scores[order[idx]])
        while end + 1 < len(order) and float(scores[order[end + 1]]) == cutoff:
            end += 1
        for pos in order[idx : end + 1]:
            seen += 1
            if not truth_pass[pos]:
                tp_fail += 1
        points.append({
            "recall": tp_fail / n_fail,
            "precision": tp_fail / seen,
            "threshold": cutoff,
        })
        idx = end + 1
    return points


def recall_at_fpr(truth_pass: Sequence[bool], scores: Sequence[float], max_fpr: float) -> dict[str, float | None]:
    """Failure recall at a target false-kill rate ``max_fpr``.

    Reports both:
    * ``step``: maximum achievable TPR at a deterministic threshold with ``FPR <= max_fpr``;
    * ``interpolated``: linear ROC interpolation at ``FPR == max_fpr`` (standard for tied/coarse scores).
    """
    if not (0.0 <= max_fpr <= 1.0):
        raise ValueError("max_fpr must be in [0, 1]")
    curve = roc_curve_fail(truth_pass, scores)
    if not curve:
        return {"step": None, "interpolated": None}
    eps = 1e-12
    feasible = [p for p in curve if float(p["fpr"]) <= max_fpr + eps]
    step_tpr = max(float(p["tpr"]) for p in feasible) if feasible else 0.0
    interp_tpr = step_tpr
    for prev, curr in zip(curve, curve[1:]):
        x0, y0 = float(prev["fpr"]), float(prev["tpr"])
        x1, y1 = float(curr["fpr"]), float(curr["tpr"])
        if x0 <= max_fpr <= x1:
            if math.isclose(x1, x0):
                interp_tpr = max(interp_tpr, y1)
            else:
                frac = (max_fpr - x0) / (x1 - x0)
                interp_tpr = y0 + frac * (y1 - y0)
            break
    return {"step": step_tpr, "interpolated": interp_tpr}


def exact_mcnemar(
    truth_pass: Sequence[bool],
    pred_a: Sequence[bool],
    pred_b: Sequence[bool],
    *,
    fail_only: bool = False,
) -> dict[str, Any]:
    """Exact two-sided McNemar test comparing correctness of binary decisions ``pred_a`` vs ``pred_b``.

    When ``fail_only=True``, restricts to true-fail items (``not truth``), testing whether
    ``pred_b`` recalls significantly more failures than ``pred_a``.
    """
    if not (len(truth_pass) == len(pred_a) == len(pred_b)):
        raise ValueError("truth_pass, pred_a, pred_b must have equal length")
    a_only = 0  # A correct, B wrong
    b_only = 0  # A wrong, B correct
    both_ok = 0
    both_wrong = 0
    n = 0
    for t, pa, pb in zip(truth_pass, pred_a, pred_b):
        if fail_only and t:
            continue
        n += 1
        ok_a = (bool(pa) == bool(t))
        ok_b = (bool(pb) == bool(t))
        if ok_a and ok_b:
            both_ok += 1
        elif ok_a and not ok_b:
            a_only += 1
        elif not ok_a and ok_b:
            b_only += 1
        else:
            both_wrong += 1
    discordant = a_only + b_only
    if discordant == 0:
        p_val = 1.0
    else:
        m_low = min(a_only, b_only)
        tail = sum(math.comb(discordant, k) for k in range(m_low + 1)) / (2 ** discordant)
        p_val = min(1.0, 2.0 * tail)
    rate_a = (both_ok + a_only) / n if n else None
    rate_b = (both_ok + b_only) / n if n else None
    return {
        "n": n,
        "fail_only": fail_only,
        "both_correct": both_ok,
        "both_wrong": both_wrong,
        "a_only_correct": a_only,
        "b_only_correct": b_only,
        "discordant": discordant,
        "rate_a": rate_a,
        "rate_b": rate_b,
        "diff_b_minus_a": (rate_b - rate_a) if (rate_a is not None and rate_b is not None) else None,
        "exact_p": p_val,
    }