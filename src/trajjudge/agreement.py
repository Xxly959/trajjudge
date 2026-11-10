"""RQ1 analysis: judge vs human vs official agreement with bootstrap CIs (pure functions)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import metrics as m

# Pre-registered before any human label existed (docs/DECISIONS.md D24).
THRESHOLDS = {"trajectory_accuracy": 2.0, "trajectory_comprehensive": 0.6}


def compare(truth: Sequence[bool], pred: Sequence[bool], *, seed: int = 0) -> dict[str, Any]:
    """Agreement of ``pred`` with ``truth`` (positive = pass), with 95% bootstrap CIs."""
    n = len(truth)
    ci = lambda f: m.bootstrap_ci(lambda idx: f([truth[i] for i in idx], [pred[i] for i in idx]), n, seed=seed)
    return {"n": n, "accuracy": m.accuracy(truth, pred), "accuracy_ci": ci(m.accuracy),
            "kappa": m.cohen_kappa(truth, pred), "kappa_ci": ci(m.cohen_kappa), "pabak": m.pabak(truth, pred),
            "confusion": m.confusion(truth, pred), "baselines": m.baselines(truth, seed=seed),
            "labels": m.label_counts(truth)}


def agreement_report(rows: Sequence[Mapping[str, Any]], *, seed: int = 0) -> dict[str, Any]:
    """Build the full RQ1 table.

    Each row: ``human`` (bool pass), ``official`` (bool pass), ``category``, and ``scores``
    (grader -> float, from one fixed judge configuration). Threshold-based decisions use ``THRESHOLDS``.
    """
    human = [bool(r["human"]) for r in rows]
    out: dict[str, Any] = {"n": len(rows), "labels": m.label_counts(human),
                           "official_vs_human": compare(human, [bool(r["official"]) for r in rows], seed=seed), "graders": {}}
    for grader, threshold in THRESHOLDS.items():
        usable = [(bool(r["human"]), r["scores"].get(grader), bool(r["official"]), r["category"]) for r in rows
                  if r["scores"].get(grader) is not None]
        if len(usable) < 2:
            continue
        truth = [u[0] for u in usable]
        pred = [u[1] >= threshold for u in usable]
        entry = compare(truth, pred, seed=seed)
        n = len(usable)
        entry["threshold"] = threshold
        entry["auc"] = m.auc(truth, [u[1] for u in usable])
        entry["auc_ci"] = m.bootstrap_ci(lambda idx: m.auc([truth[i] for i in idx], [usable[i][1] for i in idx]), n, seed=seed)
        entry["vs_official"] = compare([u[2] for u in usable], pred, seed=seed)
        cats: dict[str, dict[str, Any]] = {}
        for cat in sorted({u[3] for u in usable}):
            sel = [i for i, u in enumerate(usable) if u[3] == cat]
            cats[cat] = {"n": len(sel), "accuracy": m.accuracy([truth[i] for i in sel], [pred[i] for i in sel])}
        entry["per_category"] = cats
        out["graders"][grader] = entry
    return out


def self_consistency(round1: Mapping[str, bool], round2: Mapping[str, bool]) -> dict[str, Any] | None:
    """Agreement between a human's first and repeat labels on the shared items."""
    shared = sorted(set(round1) & set(round2))
    if len(shared) < 2:
        return None
    a, b = [round1[k] for k in shared], [round2[k] for k in shared]
    return {"n": len(shared), "agreement": m.accuracy(a, b), "kappa": m.cohen_kappa(a, b)}
