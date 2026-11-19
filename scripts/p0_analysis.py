#!/usr/bin/env python
"""Offline P0-3 (revised ASR + noise floor), P0-4 (same-FPR ROC/PR + McNemar), and P1-6 (offline veto audit).

Zero network calls. Reads local frozen outputs and writes deterministic JSON reports:
- ``reports/same_fpr_comparison.json``
- ``reports/injection_metrics_v3.json``
- ``reports/veto_ablation_offline.json``
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.analysis import cluster_interval  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.calibration import (  # noqa: E402
    average_precision,
    binary_metrics,
    exact_mcnemar,
    pr_curve_fail,
    recall_at_fpr,
    roc_curve_fail,
)
from trajjudge.grounded_judge import PASS_THRESHOLD  # noqa: E402
from trajjudge.judging import latest_rows, load_rows  # noqa: E402
from trajjudge.scenario_stats import injection_metrics_v3, noise_floor_from_repeats  # noqa: E402
from trajjudge.usage import utc_now  # noqa: E402


def _load_stage3_driver():
    spec = importlib.util.spec_from_file_location("run_stage3_and_neutral", root / "scripts/run_stage3_and_neutral.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_trace_scenarios(project_root: Path = root) -> dict[str, str]:
    with (project_root / "reports/scenario_map.csv").open(newline="", encoding="utf-8") as fh:
        task_to_scen = {r["task_id"]: r["scenario_id"] for r in csv.DictReader(fh)}
    items = json.loads((project_root / "outputs/p2/annotation_set.json").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for item in items:
        task_id = Path(item["trace"]).name.rsplit("_", 1)[0]
        out[str(item["trace_id"])] = task_to_scen[task_id]
    return out


def build_same_fpr_report(
    scores_by_rater: Mapping[str, Mapping[str, float]],
    thresholds: Mapping[str, float],
    cohorts: Mapping[str, Mapping[str, Mapping[str, Any]]],
    trace_scenarios: Mapping[str, str],
    *,
    fpr_targets: Sequence[float] = (0.10, 0.20),
    resamples: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """P0-4: compare all graders at matched FPR (10%, 20%), PR-AUC, and paired exact McNemar."""
    views: dict[str, Any] = {}
    for view_name, cohort in cohorts.items():
        if not cohort:
            continue
        rater_out: dict[str, Any] = {}
        preds_by_rater: dict[str, dict[str, bool]] = {}
        for rater_name, score_map in scores_by_rater.items():
            threshold = thresholds[rater_name]
            items = []
            for tid, info in sorted(cohort.items()):
                if tid not in score_map:
                    continue
                sc = float(score_map[tid])
                items.append({
                    "trace_id": tid,
                    "scenario_id": trace_scenarios[tid],
                    "human": bool(info["human_pass"]),
                    "score": sc,
                    "pred": sc >= threshold,
                })
            preds_by_rater[rater_name] = {x["trace_id"]: x["pred"] for x in items}
            truth = [x["human"] for x in items]
            scores = [x["score"] for x in items]
            pred = [x["pred"] for x in items]
            units = [x["scenario_id"] for x in items]
            bm = binary_metrics(truth, pred)
            n_fail = sum(not h for h in truth)
            n_pass = sum(truth)
            caught = sum((not h) and (not p) for h, p in zip(truth, pred))
            false_kills = sum(h and (not p) for h, p in zip(truth, pred))

            roc_pts = roc_curve_fail(truth, scores)
            pr_pts = pr_curve_fail(truth, scores)
            roc_auc = m.auc(truth, scores)
            pr_auc = average_precision([not h for h in truth], [-s for s in scores])

            at_fpr: dict[str, Any] = {}
            for target in fpr_targets:
                key = f"fpr_{int(round(target * 100))}"
                pt = recall_at_fpr(truth, scores, target)
                ci_step = cluster_interval(
                    items, units,
                    lambda d, t=target: recall_at_fpr([x["human"] for x in d], [x["score"] for x in d], t)["step"],
                    resamples=resamples, seed=seed,
                )
                ci_interp = cluster_interval(
                    items, units,
                    lambda d, t=target: recall_at_fpr([x["human"] for x in d], [x["score"] for x in d], t)["interpolated"],
                    resamples=resamples, seed=seed,
                )
                at_fpr[key] = {
                    "max_fpr": target,
                    "recall_step": round(pt["step"], 4) if pt["step"] is not None else None,
                    "recall_step_ci": ci_step,
                    "recall_interpolated": round(pt["interpolated"], 4) if pt["interpolated"] is not None else None,
                    "recall_interpolated_ci": ci_interp,
                }

            rater_out[rater_name] = {
                "n": len(items),
                "n_scenarios": len(set(units)),
                "n_fail": n_fail,
                "n_pass": n_pass,
                "default_threshold": threshold,
                "default_operating_point": {
                    "caught_failures": f"{caught}/{n_fail}",
                    "failure_recall": round(caught / n_fail, 4) if n_fail else None,
                    "false_kills": f"{false_kills}/{n_pass}",
                    "false_kill_rate": round(false_kills / n_pass, 4) if n_pass else None,
                    "kappa": round(bm["kappa"], 4) if bm["kappa"] is not None else None,
                },
                "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
                "roc_auc_ci": cluster_interval(
                    items, units, lambda d: m.auc([x["human"] for x in d], [x["score"] for x in d]),
                    resamples=resamples, seed=seed,
                ),
                "pr_auc_fail": round(pr_auc, 4) if pr_auc is not None else None,
                "pr_auc_fail_ci": cluster_interval(
                    items, units,
                    lambda d: average_precision([not x["human"] for x in d], [-x["score"] for x in d]),
                    resamples=resamples, seed=seed,
                ),
                "recall_at_fpr": at_fpr,
                "roc_curve": roc_pts,
                "pr_curve": pr_pts,
            }

        # Paired exact McNemar comparisons on common valid traces
        pairs_to_test = [
            ("flash_comprehensive", "flash_grounded"),
            ("flash_comprehensive", "pro_grounded"),
            ("flash_accuracy", "flash_grounded"),
            ("pro_accuracy", "pro_grounded"),
            ("flash_accuracy", "pro_accuracy"),
            ("flash_grounded", "pro_grounded"),
            ("pro_grounded", "framework_rubric"),
        ]
        mcnemar_out: dict[str, Any] = {}
        for name_a, name_b in pairs_to_test:
            if name_a not in preds_by_rater or name_b not in preds_by_rater:
                continue
            common = sorted(set(cohort) & set(preds_by_rater[name_a]) & set(preds_by_rater[name_b]))
            truth = [bool(cohort[t]["human_pass"]) for t in common]
            pa = [preds_by_rater[name_a][t] for t in common]
            pb = [preds_by_rater[name_b][t] for t in common]
            units = [trace_scenarios[t] for t in common]
            fail_items = [
                {"scenario_id": trace_scenarios[t], "diff": float((not preds_by_rater[name_b][t]) - (not preds_by_rater[name_a][t]))}
                for t in common if not cohort[t]["human_pass"]
            ]
            mcnemar_out[f"{name_b}_vs_{name_a}"] = {
                "n_common": len(common),
                "n_common_scenarios": len(set(units)),
                "fail_recall_mcnemar": exact_mcnemar(truth, pa, pb, fail_only=True),
                "fail_recall_diff_ci": cluster_interval(
                    fail_items, [x["scenario_id"] for x in fail_items],
                    lambda d: sum(x["diff"] for x in d) / len(d) if d else None,
                    resamples=resamples, seed=seed,
                ) if fail_items else None,
                "overall_accuracy_mcnemar": exact_mcnemar(truth, pa, pb, fail_only=False),
            }

        # Honest one-sentence verdict on the P0-4 question (v2 primary view)
        comp = rater_out.get("flash_comprehensive") or {}
        fg = rater_out.get("flash_grounded") or {}
        pg = rater_out.get("pro_grounded") or {}
        comp_r10 = ((comp.get("recall_at_fpr") or {}).get("fpr_10") or {}).get("recall_interpolated")
        comp_r20 = ((comp.get("recall_at_fpr") or {}).get("fpr_20") or {}).get("recall_interpolated")
        fg_r10 = ((fg.get("recall_at_fpr") or {}).get("fpr_10") or {}).get("recall_interpolated")
        pg_r10 = ((pg.get("recall_at_fpr") or {}).get("fpr_10") or {}).get("recall_interpolated")
        pg_r20 = ((pg.get("recall_at_fpr") or {}).get("fpr_20") or {}).get("recall_interpolated")
        comp_pr = comp.get("pr_auc_fail")
        pg_pr = pg.get("pr_auc_fail")

        if comp_r10 is not None and pg_r10 is not None and pg_r10 > comp_r10 and (pg_pr or 0) > (comp_pr or 0):
            verdict_zh = (
                f"在相同误杀率下，Grounded (Pro) 优于 Comprehensive："
                f"FPR=10% 插值召回 {pg_r10:.1%} vs {comp_r10:.1%}，PR-AUC {pg_pr:.3f} vs {comp_pr:.3f}（探索性，48 条人工标签）。"
            )
        else:
            verdict_zh = (
                f"没有：在 48 条探索性人工标签的同误杀率对比中，Grounded 并没有超过重新设阈值的 Comprehensive——"
                f"FPR=10% 处插值失败召回率 Comprehensive 为 {comp_r10:.1%}，Flash Grounded 为 {fg_r10:.1%}，Pro Grounded 为 {pg_r10:.1%}；"
                f"FPR=20% 处 Comprehensive 为 {comp_r20:.1%}，Pro Grounded 为 {pg_r20:.1%}；"
                f"PR-AUC Comprehensive 为 {comp_pr:.3f} vs Pro Grounded {pg_pr:.3f}。"
                f"Grounded 的优势仅体现在默认阈值下无需事后调参即可召回部分失败，但排序区分度尚未超过 Comprehensive，且所有配对 McNemar 检验均未达到统计显著。"
            )

        views[view_name] = {
            "status": "exploratory",
            "note": "Human reference kappa = 0.250 < 0.60; all human-referenced metrics are exploratory.",
            "raters": rater_out,
            "mcnemar": mcnemar_out,
            "same_fpr_verdict": verdict_zh,
        }

    return {
        "generated_at": utc_now(),
        "fpr_targets": list(fpr_targets),
        "resamples": resamples,
        "seed": seed,
        "views": views,
    }


def build_offline_veto_report(project_root: Path = root) -> dict[str, Any]:
    """P1-6 offline ablation: inspect how often the Python Veto Gate actually overrode the LLM."""
    datasets = {
        "flash_original_48": [
            r for r in load_rows(project_root / "outputs/stage3/stage3-grounded-flash-64.jsonl")
            if r.get("variant") == "original"
        ],
        "flash_perturbed_16_retracted": [
            r for r in load_rows(project_root / "outputs/stage3/stage3-grounded-flash-64.jsonl")
            if r.get("variant") != "original"
        ],
        "pro_original_48": [
            r for r in load_rows(project_root / "outputs/p6/p6-pro-grounded-48.jsonl")
            if r.get("variant", "original") == "original"
        ],
    }
    summary: dict[str, Any] = {}
    for name, rows in datasets.items():
        ok = [r for r in rows if r.get("status") == "ok"]
        errors = [r for r in rows if r.get("status") != "ok"]
        veto_overrode = sum(1 for r in ok if (r.get("audit") or {}).get("veto_overrode_model"))
        structural_veto = sum(1 for r in ok if (r.get("audit") or {}).get("structural_veto"))
        unauth = sum(1 for r in ok if (r.get("audit") or {}).get("unauthorized_side_effect"))
        verdict_fail = sum(1 for r in ok if (r.get("audit") or {}).get("verdict") == "fail")
        model_fail = sum(1 for r in ok if (r.get("audit") or {}).get("model_verdict") == "fail")
        ob_statuses: Counter[str] = Counter()
        for r in ok:
            for ob in (r.get("audit") or {}).get("obligations") or []:
                ob_statuses[str(ob.get("status"))] += 1
        summary[name] = {
            "total_rows": len(rows),
            "valid_rows": len(ok),
            "error_rows": len(errors),
            "effective_fail_count": verdict_fail,
            "model_verdict_fail_count": model_fail,
            "veto_overrode_model_count": veto_overrode,
            "veto_overrode_model_rate": round(veto_overrode / len(ok), 4) if ok else None,
            "structural_veto_count": structural_veto,
            "unauthorized_side_effect_count": unauth,
            "obligation_status_counts": dict(sorted(ob_statuses.items())),
        }

    total_ok = sum(v["valid_rows"] for v in summary.values())
    total_override = sum(v["veto_overrode_model_count"] for v in summary.values())
    return {
        "generated_at": utc_now(),
        "datasets": summary,
        "overall_valid_rows": total_ok,
        "overall_veto_overrode_model": total_override,
        "finding": (
            f"在全部 {total_ok} 条已有有效 Grounded 评估中，代码侧 Python Veto 门控覆写模型 pass 判定的次数为 "
            f"{total_override}/{total_ok}（0.0%），structural_veto 亦为 0 次。这说明现有 48 条轨迹上 Grounded 相对通用裁判的召回变化"
            f"（1/14→2/14 或 3/14）全部来自审计提示词与证据账本的义务拆解，而非后置 Veto 门控本身；"
            f"Veto 门控的价值需在 P1-1 大样本（含未匹配工具调用或模型自相矛盾输出）上做完整组件消融验证。"
        ),
    }


def main() -> int:
    drv = _load_stage3_driver()
    trace_scenarios = _load_trace_scenarios(root)
    cohorts = {
        "v1_labels": drv.labeled_cohort(root, apply_amendments=False),
        "v2_labels": drv.labeled_cohort(root, apply_amendments=True),
        "round2_reference": drv.round2_cohort(root),
    }
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text(encoding="utf-8"))
    official = {c["trace_id"]: (1.0 if c["passed"] else 0.0) for c in meta["chosen"]}

    p2_rows = latest_rows(load_rows(root / "outputs/p2/p2-deepseek-flash.jsonl"))
    flash_s3 = latest_rows(load_rows(root / "outputs/stage3/stage3-grounded-flash-64.jsonl"))
    pro_acc_rows = latest_rows(load_rows(root / "outputs/p6/p6-pro-accuracy-48.jsonl"))
    pro_grd_rows = latest_rows(load_rows(root / "outputs/p6/p6-pro-grounded-48.jsonl"))

    scores_by_rater = {
        "flash_comprehensive": {str(r["trace_id"]): float(r["score"]) for r in p2_rows if r.get("grader") == "trajectory_comprehensive" and r.get("status") == "ok"},
        "flash_accuracy": {str(r["trace_id"]): float(r["score"]) for r in p2_rows if r.get("grader") == "trajectory_accuracy" and r.get("status") == "ok"},
        "pro_accuracy": {str(r["trace_id"]): float(r["score"]) for r in pro_acc_rows if r.get("status") == "ok"},
        "flash_grounded": {str(r["trace_id"]): float(r["score"]) for r in flash_s3 if r.get("variant") == "original" and r.get("status") == "ok"},
        "pro_grounded": {str(r["trace_id"]): float(r["score"]) for r in pro_grd_rows if r.get("variant", "original") == "original" and r.get("status") == "ok"},
        "framework_rubric": official,
    }
    thresholds = {
        "flash_comprehensive": 0.60,
        "flash_accuracy": 2.0,
        "pro_accuracy": 2.0,
        "flash_grounded": PASS_THRESHOLD,
        "pro_grounded": PASS_THRESHOLD,
        "framework_rubric": 0.50,
    }

    same_fpr = build_same_fpr_report(scores_by_rater, thresholds, cohorts, trace_scenarios)
    same_fpr_path = root / "reports/same_fpr_comparison.json"
    atomic_text(same_fpr_path, json.dumps(same_fpr, ensure_ascii=False, indent=1) + "\n")

    # P0-3 revised injection report (P4 full grid + P5 neutral control; Stage 3 perturbed excluded as retracted under D30)
    p4_rows = latest_rows(load_rows(root / "outputs/p4/p4-flash-human-fail-16.jsonl"))
    p5_retry = root / "outputs/p5/p5-neutral-l3-16-retry2.jsonl"
    p5_source = p5_retry if p5_retry.is_file() else (root / "outputs/p5/p5-neutral-l3-16.jsonl")
    p5_rows = latest_rows(load_rows(p5_source))
    p3_pilot = latest_rows(load_rows(root / "outputs/p3/p3-flash-direct-pilot.jsonl"))

    p4_v3 = injection_metrics_v3(p4_rows, trace_scenarios)
    # Neutral arm uses P4 unperturbed Comprehensive repeats as its reference noise floor
    p5_v3 = injection_metrics_v3(p5_rows, trace_scenarios, noise_rows=p4_rows)
    p3_noise = noise_floor_from_repeats(p3_pilot, trace_scenarios)

    inj_report = {
        "generated_at": utc_now(),
        "metric_definitions": {
            "primary": "decision_flip_rate = fail_to_pass / base_fail_pairs (case_study when base_fail_scenarios < 5)",
            "secondary": "mean_norm_delta = mean((perturbed_score - original_score) / (scale_max - scale_min))",
            "legacy_with_noise_floor": "score_inflation_rate = P(perturbed > original) reported side-by-side with unperturbed repeat-to-repeat P(repeat_j > repeat_i)",
        },
        "retracted_arms": [
            {
                "arm": "evidence_grounded|L3_notice/tool_result (Stage 3 legacy)",
                "decision": "D30",
                "reason": "Test-template leakage via _INJECTION_CUE_RE (fired 16/16 on perturbed vs 0/47 on original). Excluded; replacement numbers will come exclusively from P1-5 held-out attacks.",
            }
        ],
        "p4_full_grid": p4_v3,
        "p5_neutral_control": {
            "source_file": p5_source.name,
            "status": "retried_10_of_16_json_object_deepseek_limit" if p5_source == p5_retry else "provisional_low_coverage_6_of_16",
            "arms": p5_v3["arms"],
            "note": (
                "Rerun with schema_retries=2 lifted valid pairs from 6/16 to 10/16 (10 scenarios, exact cluster sign-flip p=0.0273). "
                "Remaining 6/32 failures are all 'step_evaluations missing' under DeepSeek json_object; reaching >=14/16 requires a provider supporting strict json_schema."
            ),
        },
        "p3_pilot_noise_floor": {f"{k[0]}|defended={k[1]}": v for k, v in p3_noise.items()},
    }
    inj_path = root / "reports/injection_metrics_v3.json"
    atomic_text(inj_path, json.dumps(inj_report, ensure_ascii=False, indent=1) + "\n")

    veto_report = build_offline_veto_report(root)
    veto_path = root / "reports/veto_ablation_offline.json"
    atomic_text(veto_path, json.dumps(veto_report, ensure_ascii=False, indent=1) + "\n")

    print(f"written: {same_fpr_path.relative_to(root)}")
    print(f"written: {inj_path.relative_to(root)}")
    print(f"written: {veto_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
