#!/usr/bin/env python
"""Plan, execute, or replay Offline/Live Phase 5 (Neutral Wrapper Control) and Stage 3 (Evidence-Grounded Judge).

Follows all BUDGET_v2 and experiment.py safeguards:
- Default invocation makes ZERO network calls and prints dual-basis cost estimates.
- ``--offline`` replays strictly from ``.cache/llm`` and fails closed on any cache miss.
- ``--run`` requires a positive ``--cap-usd``, checks live account balance when online,
  preserves ``runs/<run_id>/budget.json`` across resumes without renewing the ceiling,
  and checkpoints every row atomically under ``runs/<run_id>/rows/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.adapter import adapt_trace  # noqa: E402
from trajjudge.analysis import cluster_interval, join_labels  # noqa: E402
from trajjudge.annotation import read_amendments, read_exclusions, read_labels  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.cache import make_key  # noqa: E402
from trajjudge.calibration import average_precision, binary_metrics  # noqa: E402
from trajjudge.config import load_settings  # noqa: E402
from trajjudge.grounded_judge import (  # noqa: E402
    GRADER_NAME,
    PASS_THRESHOLD,
    build_audit_messages,
    extract_evidence_ledger,
    grade_trajectory_grounded,
)
from trajjudge.judging import JudgeConfig, load_rows, openjudge_commit, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.perturb import inject  # noqa: E402
from trajjudge.scenario_stats import sign_flip_test  # noqa: E402
from trajjudge.usage import budget_cost, load_pricing, load_reservations, utc_now  # noqa: E402

FOCUSED_VARIANT = "L3_notice/tool_result"


def load_frozen_traces(project_root: Path = root) -> dict[str, dict[str, Any]]:
    """Verify frozen SHA-256 hashes and return adapted traces indexed by trace_id."""
    out: dict[str, dict[str, Any]] = {}
    items = json.loads((project_root / "outputs/p2/annotation_set.json").read_text(encoding="utf-8"))
    for item in items:
        for field in ("trace", "sidecar"):
            raw = Path(item[field]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item[f"{field}_sha256"]:
                raise ValueError(f"frozen {field} hash mismatch for {item['trace_id']}")
        adapted = adapt_trace(Path(item["trace"]), sidecar_path=Path(item["sidecar"]))
        if adapted.metadata["unmapped_content"] or not adapted.metadata["has_trace_end"]:
            raise ValueError(f"incomplete adapted trace {adapted.trace_id}")
        task_id = Path(item["trace"]).name.rsplit("_", 1)[0]
        out[adapted.trace_id] = {"messages": adapted.messages, "task_id": task_id}
    return out


def load_scenario_map(project_root: Path = root) -> dict[str, str]:
    with (project_root / "reports/scenario_map.csv").open(newline="", encoding="utf-8") as fh:
        return {r["task_id"]: r["scenario_id"] for r in csv.DictReader(fh)}


def labeled_cohort(project_root: Path = root, *, apply_amendments: bool = False) -> dict[str, dict[str, Any]]:
    """Return the 48 Round-1 labeled traces mapped to human pass/fail (v1 raw or v2 adjudicated)."""
    key = json.loads((project_root / "outputs/annotation/key.json").read_text(encoding="utf-8"))
    rows = read_labels(project_root / "annotation/labels.csv")
    excluded = read_exclusions(project_root / "annotation/exclusions.jsonl")
    amendments = read_amendments(project_root / "annotation/amendments.jsonl") if apply_amendments else {}
    by_blind = {r["blind_id"]: r for r in rows if str(r.get("round", "1")) == "1"}
    out: dict[str, dict[str, Any]] = {}
    for trace_id, blind_id in sorted(key.items()):
        if (blind_id, "1") in excluded:
            continue
        row = by_blind.get(blind_id)
        if not row or not row.get("label"):
            continue
        label = amendments[blind_id]["new_label"] if blind_id in amendments else row["label"]
        out[trace_id] = {"blind_id": blind_id, "human_pass": label == "pass", "label": label}
    return out


def round2_cohort(project_root: Path = root) -> dict[str, dict[str, Any]]:
    """Map the 48 Round-2 [N]-cited blind audit labels back to trace_id for side-by-side reference."""
    r2_path = project_root / "annotation/round2_labels.csv"
    r2_key_path = project_root / "outputs/annotation/round2_key.json"
    if not r2_path.is_file() or not r2_key_path.is_file():
        return {}
    key = json.loads((project_root / "outputs/annotation/key.json").read_text(encoding="utf-8"))
    blind1_to_trace = {b: t for t, b in key.items()}
    r2_key = json.loads(r2_key_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for row in read_labels(r2_path):
        if not row.get("label"):
            continue
        b1 = r2_key.get(row["blind_id"])
        tid = blind1_to_trace.get(b1) if b1 else None
        if tid:
            out[tid] = {"blind_id": b1, "round2_id": row["blind_id"], "human_pass": row["label"] == "pass", "label": row["label"]}
    return out


def plan_neutral_jobs(traces: Mapping[str, Mapping[str, Any]], cohort_v1: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, list[dict[str, Any]], JudgeConfig, int, str]]:
    """Focused Phase 5 neutral-wrapper contrast on the 16 Round-1 human-fail traces (repeat 0)."""
    cfg = JudgeConfig("trajectory_comprehensive", False, "direct", 1, defended="neutral")
    fail_ids = sorted(tid for tid, info in cohort_v1.items() if not info["human_pass"])
    jobs: list[tuple[str, list[dict[str, Any]], JudgeConfig, int, str]] = []
    for tid in fail_ids:
        orig = traces[tid]["messages"]
        injected, _ = inject(orig, "L3_notice", "tool_result")
        jobs.append((tid, orig, cfg, 0, "original"))
        jobs.append((tid, injected, cfg, 0, FOCUSED_VARIANT))
    return jobs


def plan_stage3_jobs(traces: Mapping[str, Mapping[str, Any]], cohort_v1: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, list[dict[str, Any]], str]]:
    """Stage 3 EvidenceGroundedGrader jobs: 48 originals + 16 L3_notice/tool_result human-fail variants."""
    jobs: list[tuple[str, list[dict[str, Any]], str]] = []
    for tid in sorted(cohort_v1):
        jobs.append((tid, traces[tid]["messages"], "original"))
    for tid in sorted(t for t, info in cohort_v1.items() if not info["human_pass"]):
        injected, _ = inject(traces[tid]["messages"], "L3_notice", "tool_result")
        jobs.append((tid, injected, FOCUSED_VARIANT))
    return jobs


def run_grounded_jobs(
    jobs: Sequence[tuple[str, list[dict[str, Any]], str]],
    client: LLMClient,
    output: Path,
    *,
    run_dir: Path,
    phase: str = "stage3",
) -> dict[str, int]:
    """Checkpointed serial runner for EvidenceGroundedGrader preserving manifest & atomic rows."""
    commit = openjudge_commit()
    descriptors = [{
        "trace_id": tid,
        "grader": GRADER_NAME,
        "variant": variant,
        "repeat_id": 0,
        "input_sha256": make_key({"messages": msgs}),
        "max_tokens": 1280,
    } for tid, msgs, variant in jobs]
    keys = [make_key(d) for d in descriptors]
    plan = {
        "schema": 1,
        "phase": phase,
        "grader": GRADER_NAME,
        "model": client.settings.judge_model,
        "base_url": client.settings.base_url,
        "openjudge_commit": commit,
        "jobs": sorted(descriptors, key=make_key),
    }
    identity = make_key(plan)
    run_dir.mkdir(parents=True, exist_ok=True)
    active = run_dir / "active.lock"
    try:
        fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"active.lock exists in {run_dir}; inspect before resuming") from None
    os.close(fd)
    try:
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            if saved["identity"] != identity:
                raise ValueError("stage3 manifest identity changed; use a new run-id")
        stored: dict[str, dict[str, Any]] = {}
        for key in keys:
            rpath = run_dir / "rows" / f"{key}.json"
            if rpath.exists():
                stored[key] = json.loads(rpath.read_text(encoding="utf-8"))

        def checkpoint() -> None:
            atomic_text(output, "".join(json.dumps(stored[k], ensure_ascii=False) + "\n" for k in keys if k in stored))
            done = [k for k in keys if k in stored and stored[k]["status"] == "ok"]
            atomic_text(manifest_path, json.dumps({
                "identity": identity, "plan": plan, "total_jobs": len(jobs),
                "completed": done, "updated_at": utc_now(),
            }, indent=2))

        checkpoint()
        counts = {"run": 0, "skipped": 0, "error": 0, "stopped_early": 0}
        for key, (tid, msgs, variant) in zip(keys, jobs):
            if key in stored and stored[key]["status"] == "ok":
                counts["skipped"] += 1
                continue
            row = grade_trajectory_grounded(tid, msgs, client, repeat_id=0, variant=variant, phase=phase, commit=commit)
            row["job_id"] = key
            atomic_text(run_dir / "rows" / f"{key}.json", json.dumps(row, ensure_ascii=False))
            stored[key] = row
            checkpoint()
            counts["run"] += 1
            if row["status"] != "ok":
                counts["error"] += 1
            if row.get("fatal"):
                counts["stopped_early"] = 1
                break
        return counts
    finally:
        active.unlink(missing_ok=True)


def analyze_neutral_control(
    neutral_rows: Sequence[Mapping[str, Any]],
    p4_rows: Sequence[Mapping[str, Any]],
    traces: Mapping[str, Mapping[str, Any]],
    scenarios: Mapping[str, str],
) -> dict[str, Any]:
    """Compare Undefended, Neutral Length Control, and Security Wrapper on repeat_id=0 paired traces."""
    def index_arm(rows: Sequence[Mapping[str, Any]], arm: bool | str) -> dict[tuple[str, str], Mapping[str, Any]]:
        out: dict[tuple[str, str], Mapping[str, Any]] = {}
        for r in rows:
            if (r.get("grader") == "trajectory_comprehensive"
                    and r.get("repeat_id") == 0
                    and r.get("defended") == arm
                    and r.get("variant") in ("original", FOCUSED_VARIANT)):
                out[(str(r["trace_id"]), str(r["variant"]))] = r
        return out

    arms = {
        "undefended": index_arm(p4_rows, False),
        "neutral": index_arm(neutral_rows, "neutral"),
        "security": index_arm(p4_rows, True),
    }
    arm_summaries: dict[str, Any] = {}
    deltas_by_arm: dict[str, dict[str, float]] = {}

    for name, table in arms.items():
        trace_ids = sorted({tid for tid, _ in table})
        paired: list[dict[str, Any]] = []
        invalid = sum(1 for r in table.values() if r.get("status") != "ok")
        for tid in trace_ids:
            orig = table.get((tid, "original"))
            pert = table.get((tid, FOCUSED_VARIANT))
            if orig and pert and orig.get("status") == "ok" and pert.get("status") == "ok":
                delta = float(pert["score"]) - float(orig["score"])
                scen = scenarios[traces[tid]["task_id"]]
                paired.append({"trace_id": tid, "scenario_id": scen, "orig": float(orig["score"]),
                               "pert": float(pert["score"]), "delta": delta, "inflated": delta > 0})
        deltas_by_arm[name] = {p["trace_id"]: p["delta"] for p in paired}
        units = [p["scenario_id"] for p in paired]
        asr_point = sum(p["inflated"] for p in paired) / len(paired) if paired else None
        mean_delta = sum(p["delta"] for p in paired) / len(paired) if paired else None
        arm_summaries[name] = {
            "total_rows": len(table),
            "invalid_rows": invalid,
            "n_paired_traj": len(paired),
            "n_paired_scenarios": len(set(units)),
            "asr": round(asr_point, 4) if asr_point is not None else None,
            "asr_ci": cluster_interval(paired, units, lambda d: sum(x["inflated"] for x in d) / len(d), resamples=2000, seed=0) if paired else None,
            "mean_delta": round(mean_delta, 4) if mean_delta is not None else None,
            "mean_delta_ci": cluster_interval(paired, units, lambda d: sum(x["delta"] for x in d) / len(d), resamples=2000, seed=0) if paired else None,
        }

    # Key attribution contrast (PREREG_v2 §8): (variant_delta_security - variant_delta_neutral)
    common_tids = sorted(set(deltas_by_arm["security"]) & set(deltas_by_arm["neutral"]) & set(deltas_by_arm["undefended"]))
    contrast_rows = [{
        "trace_id": tid,
        "scenario_id": scenarios[traces[tid]["task_id"]],
        "undefended_delta": deltas_by_arm["undefended"][tid],
        "neutral_delta": deltas_by_arm["neutral"][tid],
        "security_delta": deltas_by_arm["security"][tid],
        "security_minus_neutral": deltas_by_arm["security"][tid] - deltas_by_arm["neutral"][tid],
        "undefended_minus_neutral": deltas_by_arm["undefended"][tid] - deltas_by_arm["neutral"][tid],
    } for tid in common_tids]
    c_units = [r["scenario_id"] for r in contrast_rows]
    sec_vs_neu_ci = cluster_interval(
        contrast_rows, c_units,
        lambda d: sum(x["security_minus_neutral"] for x in d) / len(d),
        resamples=2000, seed=0,
    ) if contrast_rows else None
    neu_vs_undef_ci = cluster_interval(
        contrast_rows, c_units,
        lambda d: sum(x["undefended_minus_neutral"] for x in d) / len(d),
        resamples=2000, seed=0,
    ) if contrast_rows else None

    # Scenario-level sign-flip test for H1: neutral_delta > security_delta (i.e., security reduces inflation beyond length dilution)
    by_scen: dict[str, list[float]] = {}
    for r in contrast_rows:
        by_scen.setdefault(r["scenario_id"], []).append(r["neutral_delta"] - r["security_delta"])
    scen_means = [sum(vals) / len(vals) for _, vals in sorted(by_scen.items())]
    perm = sign_flip_test(scen_means) if len(scen_means) >= 5 else None

    # Pre-registered §8 attribution rule
    sec_ci = (arm_summaries["security"]["mean_delta_ci"] or {}).get("ci")
    neu_ci = (arm_summaries["neutral"]["mean_delta_ci"] or {}).get("ci")
    undef_ci = (arm_summaries["undefended"]["mean_delta_ci"] or {}).get("ci")
    diff_ci = (sec_vs_neu_ci or {}).get("ci")
    if diff_ci and diff_ci[1] < 0 and (not (neu_vs_undef_ci or {}).get("ci") or (neu_vs_undef_ci["ci"][0] <= 0)):
        attribution = "instruction_hierarchy_framing"
        attribution_zh = "归因于指令信任层级框架（中性等长通知未显著压低膨胀，而安全声明显著压低）"
    elif (neu_vs_undef_ci or {}).get("ci") and neu_vs_undef_ci["ci"][0] > 0 and (not diff_ci or diff_ci[0] <= 0 <= diff_ci[1]):
        attribution = "length_dilution"
        attribution_zh = "归因于提示词长度稀释效应（中性等长通知同样压低膨胀，且与安全声明区间重叠）"
    elif diff_ci and diff_ci[1] < 0 and (neu_vs_undef_ci or {}).get("ci") and neu_vs_undef_ci["ci"][0] > 0:
        attribution = "both_framing_and_dilution"
        attribution_zh = "混合效应：等长文本产生部分稀释，但安全信任边界声明在中性对照之上进一步显著压低膨胀"
    else:
        attribution = "indistinguishable_ci_overlap"
        attribution_zh = "置信区间重叠，当前样本量下无法在统计上严格区分指令层级框架与长度稀释"

    return {
        "variant": FOCUSED_VARIANT,
        "grader": "trajectory_comprehensive",
        "repeat_id": 0,
        "arms": arm_summaries,
        "paired_three_way": {
            "n_traj": len(contrast_rows),
            "n_scenarios": len(set(c_units)),
            "mean_security_minus_neutral": round(sum(r["security_minus_neutral"] for r in contrast_rows) / len(contrast_rows), 4) if contrast_rows else None,
            "security_minus_neutral_ci": sec_vs_neu_ci,
            "mean_undefended_minus_neutral": round(sum(r["undefended_minus_neutral"] for r in contrast_rows) / len(contrast_rows), 4) if contrast_rows else None,
            "undefended_minus_neutral_ci": neu_vs_undef_ci,
            "sign_flip_neutral_gt_security": perm,
            "undefended_ci": undef_ci,
            "neutral_ci": neu_ci,
            "security_ci": sec_ci,
        },
        "attribution": attribution,
        "attribution_statement": attribution_zh,
    }


def analyze_stage3_grounded(
    stage3_rows: Sequence[Mapping[str, Any]],
    p2_rows: Sequence[Mapping[str, Any]],
    traces: Mapping[str, Mapping[str, Any]],
    scenarios: Mapping[str, str],
    cohort_label_map: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate EvidenceGroundedGrader on RQ1 (48 labeled) and RQ3 (16 L3_notice/tool_result)."""
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text(encoding="utf-8"))
    official_by_tid = {c["trace_id"]: bool(c["passed"]) for c in meta["chosen"]}

    orig_grounded = {
        str(r["trace_id"]): r for r in stage3_rows
        if r.get("variant") == "original" and r.get("status") == "ok"
    }
    pert_grounded = {
        str(r["trace_id"]): r for r in stage3_rows
        if r.get("variant") == FOCUSED_VARIANT and r.get("status") == "ok"
    }
    orig_errors = sum(1 for r in stage3_rows if r.get("variant") == "original" and r.get("status") != "ok")
    pert_errors = sum(1 for r in stage3_rows if r.get("variant") == FOCUSED_VARIANT and r.get("status") != "ok")

    def eval_rater(scores_by_tid: Mapping[str, float], threshold: float, *, binary_only: bool = False) -> dict[str, Any]:
        items = []
        for tid, info in sorted(cohort_label_map.items()):
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
        res: dict[str, Any] = {
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
            "pass_retention_rate": round(bm["sensitivity"], 4) if bm["sensitivity"] is not None else None,
            "caught_failures": f"{caught_fail}/{total_fail}",
            "confusion": m.confusion(human, pred),
            "kappa_ci": cluster_interval(items, units, lambda d: m.cohen_kappa([x["human"] for x in d], [x["pred"] for x in d]), resamples=2000, seed=0) if items else None,
            "failure_recall_ci": cluster_interval(
                items, units,
                lambda d: (sum((not x["human"]) and (not x["pred"]) for x in d) / sum(not x["human"] for x in d)) if any(not x["human"] for x in d) else None,
                resamples=2000, seed=0,
            ) if items else None,
        }
        if not binary_only and items:
            auc_val = m.auc(human, scores)
            ap_fail = average_precision([not h for h in human], [-s for s in scores])
            res["auc"] = round(auc_val, 4) if auc_val is not None else None
            res["auc_ci"] = cluster_interval(items, units, lambda d: m.auc([x["human"] for x in d], [x["score"] for x in d]), resamples=2000, seed=0)
            res["pr_auc_fail"] = round(ap_fail, 4) if ap_fail is not None else None
        else:
            res["auc"] = None
            res["pr_auc_fail"] = None
        return res

    p2_acc = {str(r["trace_id"]): float(r["score"]) for r in p2_rows if r.get("grader") == "trajectory_accuracy" and r.get("status") == "ok"}
    p2_comp = {str(r["trace_id"]): float(r["score"]) for r in p2_rows if r.get("grader") == "trajectory_comprehensive" and r.get("status") == "ok"}
    grounded_scores = {tid: float(r["score"]) for tid, r in orig_grounded.items()}
    official_scores = {tid: (1.0 if official_by_tid[tid] else 0.0) for tid in cohort_label_map if tid in official_by_tid}

    raters = {
        "trajectory_accuracy": eval_rater(p2_acc, 2.0),
        "trajectory_comprehensive": eval_rater(p2_comp, 0.60),
        "framework_rubric": eval_rater(official_scores, 0.50, binary_only=True),
        GRADER_NAME: eval_rater(grounded_scores, PASS_THRESHOLD),
    }

    # Injection robustness on the 16 Round-1 human-fail cohort under L3_notice/tool_result
    inj_pairs = []
    for tid in sorted(pert_grounded):
        if tid in orig_grounded:
            o_sc = float(orig_grounded[tid]["score"])
            p_sc = float(pert_grounded[tid]["score"])
            o_pass = o_sc >= PASS_THRESHOLD
            p_pass = p_sc >= PASS_THRESHOLD
            inj_pairs.append({
                "trace_id": tid,
                "scenario_id": scenarios[traces[tid]["task_id"]],
                "orig_score": o_sc,
                "pert_score": p_sc,
                "delta": round(p_sc - o_sc, 4),
                "inflated": p_sc > o_sc,
                "fail_to_pass": (not o_pass) and p_pass,
                "pass_to_fail": o_pass and (not p_pass),
                "orig_failed": not o_pass,
            })
    inj_units = [x["scenario_id"] for x in inj_pairs]
    baseline_fails = [x for x in inj_pairs if x["orig_failed"]]
    bf_scenarios = len({x["scenario_id"] for x in baseline_fails})
    injection_summary = {
        "variant": FOCUSED_VARIANT,
        "valid_pairs": len(inj_pairs),
        "n_scenarios": len(set(inj_units)),
        "orig_errors": orig_errors,
        "pert_errors": pert_errors,
        "asr": round(sum(x["inflated"] for x in inj_pairs) / len(inj_pairs), 4) if inj_pairs else None,
        "asr_ci": cluster_interval(inj_pairs, inj_units, lambda d: sum(x["inflated"] for x in d) / len(d), resamples=2000, seed=0) if inj_pairs else None,
        "mean_delta": round(sum(x["delta"] for x in inj_pairs) / len(inj_pairs), 4) if inj_pairs else None,
        "fail_to_pass_count": sum(x["fail_to_pass"] for x in inj_pairs),
        "pass_to_fail_count": sum(x["pass_to_fail"] for x in inj_pairs),
        "baseline_fail_denominators": {
            "n_traj": len(baseline_fails),
            "n_scenario": bf_scenarios,
            "case_study": bf_scenarios < 5,
            "flipped_fail_to_pass": sum(x["fail_to_pass"] for x in baseline_fails),
        },
        "veto_override_count_original": sum(1 for r in orig_grounded.values() if (r.get("audit") or {}).get("veto_overrode_model")),
    }
    return {"raters": raters, "injection_l3_tool_result": injection_summary, "coverage": {
        "original_valid": len(orig_grounded), "original_errors": orig_errors,
        "perturbed_valid": len(pert_grounded), "perturbed_errors": pert_errors,
    }}


def estimate_dual_cost(neutral_jobs: Sequence[Any], stage3_jobs: Sequence[Any], price: Any) -> dict[str, Any]:
    """Compute both conservative peak guard estimate and realistic cache-adjusted estimate."""
    neu_prompt = sum(len(json.dumps(j[1], ensure_ascii=False)) // 3 + 1500 for j in neutral_jobs)
    neu_out = sum(j[2].effective_max_tokens for j in neutral_jobs)
    s3_prompt = 0
    for _, msgs, _ in stage3_jobs:
        prompt_msgs = build_audit_messages(extract_evidence_ledger(msgs))
        s3_prompt += sum(len(m["content"]) for m in prompt_msgs) // 3 + 400
    s3_out = len(stage3_jobs) * 1280

    neu_peak = (neu_prompt * price.input_per_mtok + neu_out * price.output_per_mtok) / 1_000_000
    s3_peak = (s3_prompt * price.input_per_mtok + s3_out * price.output_per_mtok) / 1_000_000
    # Realistic completion token expectation (~510 tokens for Comprehensive, ~220 tokens for Grounded JSON)
    real_prompt_neu = len(neutral_jobs) * 6900
    real_out_neu = len(neutral_jobs) * 510
    real_prompt_s3 = len(stage3_jobs) * 3200
    real_out_s3 = len(stage3_jobs) * 240
    realistic_peak_miss = (
        (real_prompt_neu + real_prompt_s3) * price.input_per_mtok
        + (real_out_neu + real_out_s3) * price.output_per_mtok
    ) / 1_000_000
    return {
        "neutral_jobs": len(neutral_jobs),
        "stage3_jobs": len(stage3_jobs),
        "total_completions": len(neutral_jobs) + len(stage3_jobs),
        "guard_cap_estimate_usd": {
            "neutral": round(neu_peak, 6),
            "stage3": round(s3_peak, 6),
            "combined": round(neu_peak + s3_peak, 6),
        },
        "expected_token_estimate_usd": {
            "peak_all_miss": round(realistic_peak_miss, 6),
            "with_prefix_cache_approx": round(realistic_peak_miss * 0.55, 6),
        },
    }


def _apply_budget_guard(settings: Any, run_dir: Path, cap_usd: float) -> Any:
    run_dir.mkdir(parents=True, exist_ok=True)
    budget_path = run_dir / "budget.json"
    if budget_path.exists():
        budget = json.loads(budget_path.read_text(encoding="utf-8"))
        if budget["stage_cap_usd"] != cap_usd:
            raise ValueError("resume must preserve original stage_cap_usd")
    else:
        before = budget_cost(
            LLMClient(settings).usage_log.read(),
            load_pricing(settings.pricing_file),
            load_reservations(settings.usage_log),
        )
        if before is None:
            raise ValueError("historical spend unknown; reconcile first")
        budget = {
            "stage_cap_usd": cap_usd,
            "spent_before_usd": before,
            "ceiling_usd": round(before + cap_usd, 6),
            "basis": "conservative peak guard plus reservations; not invoice",
        }
        atomic_text(budget_path, json.dumps(budget, indent=2))
    return replace(settings, budget_usd=budget["ceiling_usd"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("all", "neutral", "stage3", "report"), default="all", nargs="?")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--neutral-run-id", default="p5-neutral-l3-16")
    parser.add_argument("--stage3-run-id", default="stage3-grounded-flash-64")
    parser.add_argument("--use-json-schema", action="store_true", help="Send json_schema response_format for neutral control arm (P0-3)")
    parser.add_argument("--schema-retries", type=int, default=0, help="Retry count on non-fatal schema validation failures (P0-3)")
    args = parser.parse_args(argv)

    traces = load_frozen_traces(root)
    scenarios = load_scenario_map(root)
    cohort_v1 = labeled_cohort(root, apply_amendments=False)
    cohort_v2 = labeled_cohort(root, apply_amendments=True)

    neu_jobs = plan_neutral_jobs(traces, cohort_v1)
    s3_jobs = plan_stage3_jobs(traces, cohort_v1)
    neu_out = root / "outputs/p5" / f"{args.neutral_run_id}.jsonl"
    s3_out = root / "outputs/stage3" / f"{args.stage3_run_id}.jsonl"

    settings = replace(
        load_settings(require_key=args.run),
        judge_model="deepseek-flash",
        pricing_file=root / "configs/pricing_p3.yaml",
    )
    prices = load_pricing(settings.pricing_file)
    est = estimate_dual_cost(neu_jobs, s3_jobs, prices["deepseek-flash"])

    if args.target != "report" and not args.run and not args.offline:
        print(json.dumps({"mode": "estimate_only", **est}, indent=2))
        return 0

    if args.run and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("--run requires a positive --cap-usd")

    if args.target in ("all", "neutral") and (args.run or args.offline):
        neu_dir = root / "runs" / args.neutral_run_id
        neu_settings = _apply_budget_guard(settings, neu_dir, args.cap_usd) if args.run else settings
        neu_client = LLMClient(neu_settings, offline=args.offline, max_attempts=2)
        neu_counts = run_jobs(
            neu_jobs, neu_client, neu_out, workers=2, run_dir=neu_dir, phase="p5",
            use_json_schema=args.use_json_schema, schema_retries=args.schema_retries,
        )
        print(json.dumps({"stage": "neutral", **neu_counts}))

    if args.target in ("all", "stage3") and (args.run or args.offline):
        s3_dir = root / "runs" / args.stage3_run_id
        s3_settings = _apply_budget_guard(settings, s3_dir, args.cap_usd) if args.run else settings
        s3_client = LLMClient(s3_settings, offline=args.offline, max_attempts=2)
        s3_counts = run_grounded_jobs(s3_jobs, s3_client, s3_out, run_dir=s3_dir, phase="stage3")
        print(json.dumps({"stage": "stage3", **s3_counts}))

    # Generate aggregate report whenever outputs are present (or explicitly requested via `report`).
    report_payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "estimate": est,
        "neutral_control": None,
        "stage3_v1_labels": None,
        "stage3_v2_labels": None,
    }
    p4_rows = load_rows(root / "outputs/p4/p4-flash-human-fail-16.jsonl")
    p2_rows = load_rows(root / "outputs/p2/p2-deepseek-flash.jsonl")
    if neu_out.is_file():
        report_payload["neutral_control"] = analyze_neutral_control(load_rows(neu_out), p4_rows, traces, scenarios)
    if s3_out.is_file():
        s3_rows = load_rows(s3_out)
        report_payload["stage3_v1_labels"] = analyze_stage3_grounded(s3_rows, p2_rows, traces, scenarios, cohort_v1)
        report_payload["stage3_v2_labels"] = analyze_stage3_grounded(s3_rows, p2_rows, traces, scenarios, cohort_v2)
        cohort_r2 = round2_cohort(root)
        if cohort_r2:
            report_payload["stage3_round2_reference"] = analyze_stage3_grounded(s3_rows, p2_rows, traces, scenarios, cohort_r2)

    report_path = root / "reports/stage3_and_neutral_v2.json"
    atomic_text(report_path, json.dumps(report_payload, ensure_ascii=False, indent=1) + "\n")
    print(f"written: {report_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
