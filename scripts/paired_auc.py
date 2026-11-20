#!/usr/bin/env python
"""Paired ΔAUC and ITT sensitivity analysis with scenario-cluster bootstrap (Roadmap v3 Module A1).

Computes paired differences in ROC-AUC (positive class = objective failure) across two
evaluated runs on the exact same cohort, reporting both:
- ``complete_case``: paired on traces where BOTH runs have ``status == 'ok'`` and finite score;
- ``itt`` (intention-to-treat): over ALL cohort traces, treating missing/error rows as
  predicted failure with ``raw_score = 0.0``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def roc_auc_fail(y_fail: Sequence[bool], fail_scores: Sequence[float]) -> float | None:
    """Mann-Whitney U ROC-AUC for positive class ``y_fail=True`` with 0.5 tie handling."""
    pos = [float(s) for y, s in zip(y_fail, fail_scores) if y]
    neg = [float(s) for y, s in zip(y_fail, fail_scores) if not y]
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def load_run_rows_by_trace(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Load latest per-trace row dictionary from ``<run_dir>/rows/*.json``."""
    rows_dir = run_dir / "rows"
    if not rows_dir.is_dir():
        raise FileNotFoundError(f"missing rows dir: {rows_dir}")
    out: dict[str, dict[str, Any]] = {}
    for rf in sorted(rows_dir.glob("*.json")):
        row = json.loads(rf.read_text(encoding="utf-8"))
        tid = row.get("trace_id")
        if tid:
            prev = out.get(tid)
            if prev is None or str(row.get("timestamp", "")) >= str(prev.get("timestamp", "")):
                out[tid] = row
    return out


def infer_grader(rows: Mapping[str, Mapping[str, Any]], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for row in rows.values():
        g = row.get("grader")
        if g:
            return str(g)
    raise ValueError("cannot infer grader name from empty run")


def row_to_fail_score(
    row: Mapping[str, Any] | None,
    grader: str,
    *,
    itt: bool = False,
) -> float | None:
    """Map a judge row to failure score (higher = more likely failure).

    In ITT mode, missing or invalid rows receive ``raw_score = 0.0`` (predicted fail).
    For accuracy scale ``[1, 3]``, fail score is ``3.0 - raw_score`` (so ``0.0 -> 3.0``);
    for ``[0, 1]`` graders (``evidence_grounded``, ``trajectory_comprehensive``), fail score
    is ``1.0 - raw_score`` (so ``0.0 -> 1.0``).
    """
    valid = (
        row is not None
        and row.get("status") == "ok"
        and type(row.get("score")) in (int, float)
        and math.isfinite(float(row["score"]))
    )
    if not valid:
        if not itt:
            return None
        raw = 0.0
    else:
        raw = float(row["score"])  # type: ignore[index]
    if grader == "trajectory_accuracy":
        return 3.0 - raw
    return 1.0 - raw


def compute_paired_delta_auc(
    cohort_traces: Sequence[Mapping[str, Any]],
    rows_a: Mapping[str, Mapping[str, Any]],
    rows_b: Mapping[str, Mapping[str, Any]],
    *,
    grader_a: str | None = None,
    grader_b: str | None = None,
    mode: str = "complete_case",
    resamples: int = 2000,
    seed: int = 0,
    subset_trace_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Compute paired ΔAUC (AUC_A - AUC_B) with scenario-cluster bootstrap 95% CI & two-sided p."""
    if mode not in ("complete_case", "itt"):
        raise ValueError(f"unknown mode {mode!r}")
    ga = infer_grader(rows_a, grader_a)
    gb = infer_grader(rows_b, grader_b)
    itt = mode == "itt"

    items: list[tuple[str, bool, float, float]] = []
    n_candidates = 0
    for tr in sorted(cohort_traces, key=lambda x: str(x["trace_id"])):
        tid = str(tr["trace_id"])
        if subset_trace_ids is not None and tid not in subset_trace_ids:
            continue
        n_candidates += 1
        sa = row_to_fail_score(rows_a.get(tid), ga, itt=itt)
        sb = row_to_fail_score(rows_b.get(tid), gb, itt=itt)
        if sa is None or sb is None:
            continue
        items.append((str(tr["scenario_id"]), not bool(tr["objective_pass"]), sa, sb))

    n_valid = len(items)
    by_sc: dict[str, list[tuple[str, bool, float, float]]] = defaultdict(list)
    for it in items:
        by_sc[it[0]].append(it)
    scs = sorted(by_sc)

    if not items:
        return {
            "mode": mode,
            "n_candidates": n_candidates,
            "n_paired": 0,
            "n_scenarios": 0,
            "auc_a": None,
            "auc_b": None,
            "delta_auc": None,
            "ci_95": None,
            "p_value": None,
            "status": "not_estimable",
        }

    y = [x[1] for x in items]
    sa_list = [x[2] for x in items]
    sb_list = [x[3] for x in items]
    auc_a = roc_auc_fail(y, sa_list)
    auc_b = roc_auc_fail(y, sb_list)
    if auc_a is None or auc_b is None:
        return {
            "mode": mode,
            "n_candidates": n_candidates,
            "n_paired": n_valid,
            "n_scenarios": len(scs),
            "auc_a": auc_a,
            "auc_b": auc_b,
            "delta_auc": None,
            "ci_95": None,
            "p_value": None,
            "status": "not_estimable",
        }
    delta = auc_a - auc_b

    rng = random.Random(seed)
    deltas: list[float] = []
    undefined = 0
    for _ in range(resamples):
        samp = []
        for sc in rng.choices(scs, k=len(scs)):
            samp.extend(by_sc[sc])
        aa = roc_auc_fail([x[1] for x in samp], [x[2] for x in samp])
        ab = roc_auc_fail([x[1] for x in samp], [x[3] for x in samp])
        if aa is None or ab is None:
            undefined += 1
        else:
            deltas.append(aa - ab)

    if len(deltas) < max(2, resamples // 2):
        ci = None
        p_val = None
        status = "not_estimable"
    else:
        deltas.sort()
        lo = deltas[int(0.025 * (len(deltas) - 1))]
        hi = deltas[int(0.975 * (len(deltas) - 1))]
        p_le = sum(1 for d in deltas if d <= 0.0) / len(deltas)
        p_ge = sum(1 for d in deltas if d >= 0.0) / len(deltas)
        p_val = round(min(1.0, 2.0 * min(p_le, p_ge)), 6)
        ci = [round(lo, 4), round(hi, 4)]
        status = "ok"

    return {
        "mode": mode,
        "n_candidates": n_candidates,
        "n_paired": n_valid,
        "n_scenarios": len(scs),
        "n_fail": sum(1 for x in items if x[1]),
        "n_pass": sum(1 for x in items if not x[1]),
        "auc_a": round(auc_a, 4),
        "auc_b": round(auc_b, 4),
        "delta_auc": round(delta, 4),
        "ci_95": ci,
        "p_value": p_val,
        "resamples": resamples,
        "seed": seed,
        "undefined_draws": undefined,
        "status": status,
    }


def _pair_both_modes(
    cohort_traces: Sequence[Mapping[str, Any]],
    run_a: Path,
    run_b: Path,
    *,
    label_a: str,
    label_b: str,
    resamples: int = 2000,
    seed: int = 0,
    subset_trace_ids: set[str] | None = None,
) -> dict[str, Any]:
    rows_a = load_run_rows_by_trace(run_a)
    rows_b = load_run_rows_by_trace(run_b)
    return {
        "label_a": label_a,
        "label_b": label_b,
        "run_a": run_a.name,
        "run_b": run_b.name,
        "complete_case": compute_paired_delta_auc(
            cohort_traces, rows_a, rows_b, mode="complete_case",
            resamples=resamples, seed=seed, subset_trace_ids=subset_trace_ids,
        ),
        "itt": compute_paired_delta_auc(
            cohort_traces, rows_a, rows_b, mode="itt",
            resamples=resamples, seed=seed, subset_trace_ids=subset_trace_ids,
        ),
    }


def build_all_v3_report(*, resamples: int = 2000, seed: int = 0) -> dict[str, Any]:
    """Generate ``reports/paired_auc_v3.json`` covering P1 main & P1-6 ablation comparisons."""
    cohort_path = root / "outputs/p1/taubench_cohort.json"
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))["traces"]
    runs_root = root / "runs"

    main_specs = [
        ("grd_glm_flash_vs_comp_glm_flash", "Grounded-GLMFlash", "p1-hubcore_glm_flash-evidence_grounded", "Comprehensive-GLMFlash", "p1-hubcore_glm_flash-comprehensive"),
        ("grd_glm_flash_vs_comp_glm_flash_d33", "Grounded-GLMFlash", "p1-hubcore_glm_flash-evidence_grounded", "Comprehensive-GLMFlash (D33)", "p1d33-hubcore_glm_flash-comprehensive"),
        ("comp_glm_d33_vs_pred33", "Comprehensive-GLMFlash (D33)", "p1d33-hubcore_glm_flash-comprehensive", "Comprehensive-GLMFlash (pre-D33)", "p1-hubcore_glm_flash-comprehensive"),
        ("grd_glm_flash_vs_acc_glm_flash", "Grounded-GLMFlash", "p1-hubcore_glm_flash-evidence_grounded", "Accuracy-GLMFlash", "p1-hubcore_glm_flash-accuracy"),
        ("grd_glm_flash_vs_acc_glm_pro", "Grounded-GLMFlash", "p1-hubcore_glm_flash-evidence_grounded", "Accuracy-GLMPro", "p1-hubcore_glm_pro-accuracy"),
        ("grd_ds_flash_vs_acc_ds_flash", "Grounded-DSFlash", "p1-deepseek-evidence_grounded", "Accuracy-DSFlash", "p1-deepseek-accuracy"),
        ("grd_ds_flash_vs_comp_ds_flash", "Grounded-DSFlash", "p1-deepseek-evidence_grounded", "Comprehensive-DSFlash", "p1-deepseek-comprehensive"),
        ("acc_ds_flash_vs_comp_ds_flash", "Accuracy-DSFlash", "p1-deepseek-accuracy", "Comprehensive-DSFlash", "p1-deepseek-comprehensive"),
        ("grd_glm_pro_vs_acc_glm_pro", "Grounded-GLMPro", "p1-hubcore_glm_pro-evidence_grounded", "Accuracy-GLMPro", "p1-hubcore_glm_pro-accuracy"),
        ("acc_glm_pro_vs_acc_glm_flash", "Accuracy-GLMPro", "p1-hubcore_glm_pro-accuracy", "Accuracy-GLMFlash", "p1-hubcore_glm_flash-accuracy"),
        ("grd_glm_flash_vs_grd_ds_flash", "Grounded-GLMFlash", "p1-hubcore_glm_flash-evidence_grounded", "Grounded-DSFlash", "p1-deepseek-evidence_grounded"),
    ]
    main_pairs: dict[str, Any] = {}
    for key, la, ra, lb, rb in main_specs:
        if not (runs_root / ra).is_dir() or not (runs_root / rb).is_dir():
            continue
        main_pairs[key] = _pair_both_modes(
            cohort, runs_root / ra, runs_root / rb, label_a=la, label_b=lb, resamples=resamples, seed=seed,
        )

    pooled_300: dict[str, Any] = {}
    val_cohort_path = root / "outputs/p1_val/taubench_val_v3.json"
    if (
        val_cohort_path.is_file()
        and (runs_root / "p1d33-hubcore_glm_flash-comprehensive").is_dir()
        and (runs_root / "p1val-hubcore_glm_flash-comprehensive").is_dir()
    ):
        val_cohort = json.loads(val_cohort_path.read_text(encoding="utf-8"))["traces"]
        pooled_traces = list(cohort) + list(val_cohort)
        g_pool = {
            **load_run_rows_by_trace(runs_root / "p1-hubcore_glm_flash-evidence_grounded"),
            **load_run_rows_by_trace(runs_root / "p1val-hubcore_glm_flash-evidence_grounded"),
        }
        c_pool = {
            **load_run_rows_by_trace(runs_root / "p1d33-hubcore_glm_flash-comprehensive"),
            **load_run_rows_by_trace(runs_root / "p1val-hubcore_glm_flash-comprehensive"),
        }
        a_pool = {
            **load_run_rows_by_trace(runs_root / "p1-hubcore_glm_flash-accuracy"),
            **load_run_rows_by_trace(runs_root / "p1val-hubcore_glm_flash-accuracy"),
        }
        for key, la, rows_a, ga, lb, rows_b, gb in (
            ("pooled300_grd_vs_comp_d33", "Grounded-GLMFlash (300)", g_pool, "evidence_grounded", "Comprehensive-GLMFlash D33 (300)", c_pool, "trajectory_comprehensive"),
            ("pooled300_grd_vs_acc", "Grounded-GLMFlash (300)", g_pool, "evidence_grounded", "Accuracy-GLMFlash (300)", a_pool, "trajectory_accuracy"),
        ):
            pooled_300[key] = {
                "label_a": la,
                "label_b": lb,
                "complete_case": compute_paired_delta_auc(
                    pooled_traces, rows_a, rows_b, grader_a=ga, grader_b=gb, mode="complete_case",
                    resamples=resamples, seed=seed,
                ),
                "itt": compute_paired_delta_auc(
                    pooled_traces, rows_a, rows_b, grader_a=ga, grader_b=gb, mode="itt",
                    resamples=resamples, seed=seed,
                ),
            }

    abl_full_rows = load_run_rows_by_trace(runs_root / "p16-hubcore_glm_flash-full-v0-n60")
    abl_tids = set(abl_full_rows.keys())
    abl_specs = [
        ("full_vs_no_veto", "Ablation full", "p16-hubcore_glm_flash-full-v0-n60", "no_veto", "p16-hubcore_glm_flash-no_veto-v0-n60"),
        ("full_vs_no_quarantine", "Ablation full", "p16-hubcore_glm_flash-full-v0-n60", "no_quarantine", "p16-hubcore_glm_flash-no_quarantine-v0-n60"),
        ("full_vs_no_ledger", "Ablation full", "p16-hubcore_glm_flash-full-v0-n60", "no_ledger", "p16-hubcore_glm_flash-no_ledger-v0-n60"),
    ]
    ablation_pairs: dict[str, Any] = {}
    for key, la, ra, lb, rb in abl_specs:
        ablation_pairs[key] = _pair_both_modes(
            cohort, runs_root / ra, runs_root / rb, label_a=la, label_b=lb,
            resamples=resamples, seed=seed, subset_trace_ids=abl_tids,
        )

    subset_check = _pair_both_modes(
        cohort,
        runs_root / "p1-hubcore_glm_flash-evidence_grounded",
        runs_root / "p16-hubcore_glm_flash-full-v0-n60",
        label_a="Main Grounded-GLMFlash (on 60 subset)",
        label_b="Ablation full-v0 (60 subset)",
        resamples=resamples,
        seed=seed,
        subset_trace_ids=abl_tids,
    )

    report = {
        "generated_at": _utc_now(),
        "bootstrap": {"unit": "scenario_id", "resamples": resamples, "seed": seed},
        "itt_rule": "missing/error rows assigned predicted failure with raw_score=0.0",
        "main_cohort": main_pairs,
        "pooled_300_fair_d33": pooled_300,
        "ablation_60": ablation_pairs,
        "ablation_subset_easiness_check": {
            "n_subset": len(abl_tids),
            "main_full_200_auc_cc": main_pairs["grd_glm_flash_vs_acc_glm_flash"]["complete_case"]["auc_a"],
            "main_on_60_vs_abl_full": subset_check,
        },
    }
    atomic_text(root / "reports/paired_auc_v3.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", type=Path)
    parser.add_argument("--run-b", type=Path)
    parser.add_argument("--cohort", type=Path, default=root / "outputs/p1/taubench_cohort.json")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all-v3", action="store_true")
    args = parser.parse_args(argv)

    if args.all_v3:
        rep = build_all_v3_report(resamples=args.resamples, seed=args.seed)
        summary = {
            section: {
                k: {
                    "cc": f"{v['complete_case']['delta_auc']} {v['complete_case']['ci_95']} p={v['complete_case']['p_value']} (n={v['complete_case']['n_paired']})",
                    "itt": f"{v['itt']['delta_auc']} {v['itt']['ci_95']} p={v['itt']['p_value']} (n={v['itt']['n_paired']})",
                }
                for k, v in pairs.items()
            }
            for section, pairs in (("main_cohort", rep["main_cohort"]), ("ablation_60", rep["ablation_60"]))
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not args.run_a or not args.run_b:
        parser.error("provide either --all-v3 or both --run-a and --run-b")

    cohort_data = json.loads(args.cohort.read_text(encoding="utf-8"))
    cohort_traces = cohort_data["traces"] if isinstance(cohort_data, dict) else cohort_data
    res = _pair_both_modes(
        cohort_traces, args.run_a, args.run_b,
        label_a=args.run_a.name, label_b=args.run_b.name,
        resamples=args.resamples, seed=args.seed,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
