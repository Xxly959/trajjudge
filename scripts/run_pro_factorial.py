#!/usr/bin/env python
"""2x2 Factorial Experiment: Judge Model Scale (Flash vs v4-Pro) x Judge Architecture (Generic vs Evidence-Grounded).

Pre-registered under PREREG_v2 §12 CC-3.
Evaluates ``deepseek-v4-pro`` (`thinking=off`, `direct`, `repeat_id=0`) on the 48 labeled P2 trajectories
under both upstream ``TrajectoryAccuracyGrader`` and ``EvidenceGroundedGrader``, then computes the full
2x2 factorial table, scenario-cluster CIs, paired contrasts, and quality-cost Pareto metrics.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.analysis import cluster_interval  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.calibration import average_precision, binary_metrics  # noqa: E402
from trajjudge.config import load_settings  # noqa: E402
from trajjudge.grounded_judge import (  # noqa: E402
    GRADER_NAME,
    PASS_THRESHOLD,
    build_audit_messages,
    extract_evidence_ledger,
)
from trajjudge.judging import JudgeConfig, load_rows, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.scenario_stats import sign_flip_test  # noqa: E402
from trajjudge.usage import budget_cost, load_pricing, load_reservations, utc_now  # noqa: E402

import importlib.util  # noqa: E402


def _load_stage3_driver():
    spec = importlib.util.spec_from_file_location("run_stage3_and_neutral", root / "scripts/run_stage3_and_neutral.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def estimate_pro_cost(acc_jobs: Sequence[Any], grounded_jobs: Sequence[Any], price: Any) -> dict[str, Any]:
    acc_in_bytes = sum(len(json.dumps(j[1], ensure_ascii=False).encode("utf-8")) + 4096 for j in acc_jobs)
    acc_out_cap = sum(j[2].effective_max_tokens for j in acc_jobs)
    grd_in_bytes = 0
    for _, msgs, _ in grounded_jobs:
        pmsgs = build_audit_messages(extract_evidence_ledger(msgs))
        grd_in_bytes += sum(len(x["content"].encode("utf-8")) for x in pmsgs) + 4096
    grd_out_cap = len(grounded_jobs) * 1280

    # LLMClient._check_budget byte bound (1 attempt) vs expected actual tokens
    acc_byte_guard = (acc_in_bytes * price.input_per_mtok + acc_out_cap * price.output_per_mtok) / 1_000_000
    grd_byte_guard = (grd_in_bytes * price.input_per_mtok + grd_out_cap * price.output_per_mtok) / 1_000_000

    # Expected real tokens (~10k prompt / 120 out for Accuracy; ~8.3k prompt / 650 out for Grounded)
    expected_peak_usd = (
        (len(acc_jobs) * 10000 + len(grounded_jobs) * 8400) * price.input_per_mtok
        + (len(acc_jobs) * 120 + len(grounded_jobs) * 650) * price.output_per_mtok
    ) / 1_000_000
    return {
        "pro_accuracy_jobs": len(acc_jobs),
        "pro_grounded_jobs": len(grounded_jobs),
        "total_completions": len(acc_jobs) + len(grounded_jobs),
        "single_attempt_byte_guard_usd": {
            "pro_accuracy": round(acc_byte_guard, 6),
            "pro_grounded": round(grd_byte_guard, 6),
            "combined": round(acc_byte_guard + grd_byte_guard, 6),
        },
        "expected_token_cost_usd": {
            "peak_cache_miss": round(expected_peak_usd, 6),
            "off_peak_or_cached_approx": round(expected_peak_usd * 0.50, 6),
        },
    }


def _apply_budget(settings: Any, run_dir: Path, cap_usd: float) -> Any:
    run_dir.mkdir(parents=True, exist_ok=True)
    bpath = run_dir / "budget.json"
    if bpath.exists():
        saved = json.loads(bpath.read_text(encoding="utf-8"))
        if saved["stage_cap_usd"] != cap_usd:
            raise ValueError("resume must preserve original stage_cap_usd")
    else:
        before = budget_cost(
            LLMClient(settings).usage_log.read(),
            load_pricing(settings.pricing_file),
            load_reservations(settings.usage_log),
        )
        if before is None:
            raise ValueError("historical spend unknown")
        saved = {
            "stage_cap_usd": cap_usd,
            "spent_before_usd": before,
            "ceiling_usd": round(before + cap_usd, 6),
            "basis": "conservative peak guard plus reservations; not invoice",
        }
        atomic_text(bpath, json.dumps(saved, indent=2))
    return replace(settings, budget_usd=saved["ceiling_usd"])


def evaluate_cell(
    scores_by_tid: Mapping[str, float],
    threshold: float,
    cohort: Mapping[str, Mapping[str, Any]],
    traces: Mapping[str, Mapping[str, Any]],
    scenarios: Mapping[str, str],
    *,
    binary_only: bool = False,
) -> dict[str, Any]:
    items = []
    for tid, info in sorted(cohort.items()):
        if tid not in scores_by_tid:
            continue
        sc = float(scores_by_tid[tid])
        items.append({
            "trace_id": tid,
            "scenario_id": scenarios[traces[tid]["task_id"]],
            "human": bool(info["human_pass"]),
            "pred": sc >= threshold,
            "score": sc,
        })
    units = [x["scenario_id"] for x in items]
    human = [x["human"] for x in items]
    pred = [x["pred"] for x in items]
    scores = [x["score"] for x in items]
    bm = binary_metrics(human, pred)
    total_fail = sum(not h for h in human)
    caught_fail = sum((not h) and (not p) for h, p in zip(human, pred))
    out: dict[str, Any] = {
        "n": len(items),
        "n_scenarios": len(set(units)),
        "threshold": threshold,
        "accuracy": round(m.accuracy(human, pred), 4) if items else None,
        "kappa": round(m.cohen_kappa(human, pred), 4) if items and m.cohen_kappa(human, pred) is not None else None,
        "pabak": round(m.pabak(human, pred), 4) if items else None,
        "balanced_accuracy": round(bm["balanced_accuracy"], 4) if bm["balanced_accuracy"] is not None else None,
        "failure_recall": round(caught_fail / total_fail, 4) if total_fail else None,
        "miss_rate": round(bm["miss_rate"], 4) if bm["miss_rate"] is not None else None,
        "false_kill_rate": round(1.0 - bm["sensitivity"], 4) if bm["sensitivity"] is not None else None,
        "caught_failures": f"{caught_fail}/{total_fail}",
        "confusion": m.confusion(human, pred) if items else None,
        "kappa_ci": cluster_interval(items, units, lambda d: m.cohen_kappa([x["human"] for x in d], [x["pred"] for x in d]), resamples=2000, seed=0) if items else None,
        "failure_recall_ci": cluster_interval(
            items, units,
            lambda d: (sum((not x["human"]) and (not x["pred"]) for x in d) / sum(not x["human"] for x in d)) if any(not x["human"] for x in d) else None,
            resamples=2000, seed=0,
        ) if items else None,
    }
    if not binary_only and items:
        auc_v = m.auc(human, scores)
        ap_f = average_precision([not h for h in human], [-s for s in scores])
        out["auc"] = round(auc_v, 4) if auc_v is not None else None
        out["auc_ci"] = cluster_interval(items, units, lambda d: m.auc([x["human"] for x in d], [x["score"] for x in d]), resamples=2000, seed=0)
        out["pr_auc_fail"] = round(ap_f, 4) if ap_f is not None else None
    else:
        out["auc"] = None
        out["pr_auc_fail"] = None
    return out


def factorial_contrasts(
    cells_pred: Mapping[str, Mapping[str, bool]],
    cohort: Mapping[str, Mapping[str, Any]],
    traces: Mapping[str, Mapping[str, Any]],
    scenarios: Mapping[str, str],
) -> dict[str, Any]:
    """Paired trajectory correctness & failure-catch contrasts across the 2x2 factorial grid."""
    common = sorted(
        set(cohort)
        & set(cells_pred.get("flash_accuracy", {}))
        & set(cells_pred.get("flash_grounded", {}))
        & set(cells_pred.get("pro_accuracy", {}))
        & set(cells_pred.get("pro_grounded", {}))
    )
    if not common:
        return {"n_common": 0}

    def pair_diff(key_b: str, key_a: str, *, fail_only: bool = False) -> dict[str, Any]:
        rows = []
        for tid in common:
            h = bool(cohort[tid]["human_pass"])
            if fail_only and h:
                continue
            corr_a = float(cells_pred[key_a][tid] == h)
            corr_b = float(cells_pred[key_b][tid] == h)
            rows.append({
                "trace_id": tid,
                "scenario_id": scenarios[traces[tid]["task_id"]],
                "diff": corr_b - corr_a,
            })
        if not rows:
            return {"n": 0}
        units = [r["scenario_id"] for r in rows]
        by_scen: dict[str, list[float]] = {}
        for r in rows:
            by_scen.setdefault(r["scenario_id"], []).append(r["diff"])
        scen_means = [sum(v) / len(v) for _, v in sorted(by_scen.items())]
        return {
            "n_traj": len(rows),
            "n_scenarios": len(set(units)),
            "mean_gain": round(sum(r["diff"] for r in rows) / len(rows), 4),
            "ci": cluster_interval(rows, units, lambda d: sum(x["diff"] for x in d) / len(d), resamples=2000, seed=0),
            "sign_flip": sign_flip_test(scen_means) if len(scen_means) >= 5 else None,
        }

    return {
        "n_common_traj": len(common),
        "n_common_scenarios": len({scenarios[traces[t]["task_id"]] for t in common}),
        "scale_effect_on_generic_fail_recall": pair_diff("pro_accuracy", "flash_accuracy", fail_only=True),
        "arch_effect_on_flash_fail_recall": pair_diff("flash_grounded", "flash_accuracy", fail_only=True),
        "arch_effect_on_pro_fail_recall": pair_diff("pro_grounded", "pro_accuracy", fail_only=True),
        "combined_pro_grounded_vs_flash_generic_fail_recall": pair_diff("pro_grounded", "flash_accuracy", fail_only=True),
        "combined_overall_accuracy_gain": pair_diff("pro_grounded", "flash_accuracy", fail_only=False),
    }


def build_factorial_report(drv: Any, acc_out: Path, grd_out: Path) -> dict[str, Any]:
    traces = drv.load_frozen_traces(root)
    scenarios = drv.load_scenario_map(root)
    cohorts = {
        "v1_labels": drv.labeled_cohort(root, apply_amendments=False),
        "v2_labels": drv.labeled_cohort(root, apply_amendments=True),
        "round2_reference": drv.round2_cohort(root),
    }
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text(encoding="utf-8"))
    official = {c["trace_id"]: (1.0 if c["passed"] else 0.0) for c in meta["chosen"]}

    p2_rows = load_rows(root / "outputs/p2/p2-deepseek-flash.jsonl")
    flash_s3 = load_rows(root / "outputs/stage3/stage3-grounded-flash-64.jsonl")
    pro_acc_rows = load_rows(acc_out)
    pro_grd_rows = load_rows(grd_out)

    flash_acc = {str(r["trace_id"]): float(r["score"]) for r in p2_rows if r.get("grader") == "trajectory_accuracy" and r.get("status") == "ok"}
    flash_comp = {str(r["trace_id"]): float(r["score"]) for r in p2_rows if r.get("grader") == "trajectory_comprehensive" and r.get("status") == "ok"}
    flash_grd = {str(r["trace_id"]): float(r["score"]) for r in flash_s3 if r.get("variant") == "original" and r.get("status") == "ok"}
    pro_acc = {str(r["trace_id"]): float(r["score"]) for r in pro_acc_rows if r.get("status") == "ok"}
    pro_grd = {str(r["trace_id"]): float(r["score"]) for r in pro_grd_rows if r.get("variant") == "original" and r.get("status") == "ok"}

    cells_pred = {
        "flash_accuracy": {t: s >= 2.0 for t, s in flash_acc.items()},
        "flash_grounded": {t: s >= PASS_THRESHOLD for t, s in flash_grd.items()},
        "pro_accuracy": {t: s >= 2.0 for t, s in pro_acc.items()},
        "pro_grounded": {t: s >= PASS_THRESHOLD for t, s in pro_grd.items()},
    }

    views: dict[str, Any] = {}
    for name, cohort in cohorts.items():
        if not cohort:
            continue
        views[name] = {
            "cells": {
                "flash_comprehensive": evaluate_cell(flash_comp, 0.60, cohort, traces, scenarios),
                "flash_accuracy": evaluate_cell(flash_acc, 2.0, cohort, traces, scenarios),
                "flash_grounded": evaluate_cell(flash_grd, PASS_THRESHOLD, cohort, traces, scenarios),
                "pro_accuracy": evaluate_cell(pro_acc, 2.0, cohort, traces, scenarios),
                "pro_grounded": evaluate_cell(pro_grd, PASS_THRESHOLD, cohort, traces, scenarios),
                "framework_rubric": evaluate_cell(official, 0.50, cohort, traces, scenarios, binary_only=True),
            },
            "contrasts": factorial_contrasts(cells_pred, cohort, traces, scenarios),
        }

    return {
        "generated_at": utc_now(),
        "coverage": {
            "pro_accuracy_valid": len(pro_acc),
            "pro_accuracy_errors": sum(1 for r in pro_acc_rows if r.get("status") != "ok"),
            "pro_grounded_valid": len(pro_grd),
            "pro_grounded_errors": sum(1 for r in pro_grd_rows if r.get("status") != "ok"),
            "flash_grounded_valid": len(flash_grd),
        },
        "views": views,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("all", "pro-accuracy", "pro-grounded", "report"), default="all", nargs="?")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--acc-run-id", default="p6-pro-accuracy-48")
    parser.add_argument("--grd-run-id", default="p6-pro-grounded-48")
    args = parser.parse_args(argv)

    drv = _load_stage3_driver()
    traces = drv.load_frozen_traces(root)
    cohort_v1 = drv.labeled_cohort(root, apply_amendments=False)

    cfg_acc = JudgeConfig("trajectory_accuracy", False, "direct", 1, defended=False)
    acc_jobs = [(tid, traces[tid]["messages"], cfg_acc, 0, "original") for tid in sorted(cohort_v1)]
    grd_jobs = [(tid, traces[tid]["messages"], "original") for tid in sorted(cohort_v1)]

    acc_out = root / "outputs/p6" / f"{args.acc_run_id}.jsonl"
    grd_out = root / "outputs/p6" / f"{args.grd_run_id}.jsonl"

    settings = replace(
        load_settings(require_key=args.run),
        judge_model="deepseek-v4-pro",
        pricing_file=root / "configs/pricing_p3.yaml",
    )
    prices = load_pricing(settings.pricing_file)
    est = estimate_pro_cost(acc_jobs, grd_jobs, prices["deepseek-v4-pro"])

    if args.target != "report" and not args.run and not args.offline:
        print(json.dumps({"mode": "estimate_only", **est}, indent=2))
        return 0

    if args.run and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("--run requires a positive --cap-usd")

    if args.target in ("all", "pro-accuracy") and (args.run or args.offline):
        acc_dir = root / "runs" / args.acc_run_id
        acc_settings = _apply_budget(settings, acc_dir, args.cap_usd) if args.run else settings
        acc_client = LLMClient(acc_settings, offline=args.offline, max_attempts=1)
        # Note: tag in p3-pro-direct-4 used phase="p3"; cache keys do NOT include tag, so cached pro calls hit!
        counts = run_jobs(acc_jobs, acc_client, acc_out, workers=2, run_dir=acc_dir, phase="p6")
        print(json.dumps({"stage": "pro-accuracy", **counts}))

    if args.target in ("all", "pro-grounded") and (args.run or args.offline):
        grd_dir = root / "runs" / args.grd_run_id
        grd_settings = _apply_budget(settings, grd_dir, args.cap_usd) if args.run else settings
        grd_client = LLMClient(grd_settings, offline=args.offline, max_attempts=2, timeout=120.0)
        counts = drv.run_grounded_jobs(grd_jobs, grd_client, grd_out, run_dir=grd_dir, phase="p6_grounded")
        print(json.dumps({"stage": "pro-grounded", **counts}))

    report = build_factorial_report(drv, acc_out, grd_out)
    report["estimate"] = est
    out_path = root / "reports/pro_factorial_v2.json"
    atomic_text(out_path, json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(f"written: {out_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
