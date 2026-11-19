#!/usr/bin/env python
"""P1-1 Objective-Label τ-bench Benchmark Pipeline (build cohort, rule baselines, multi-vendor judging, & report).

Follows PREREG_v3 and all TrajJudge safety guards:
- Raw τ-bench traces stay local under gitignored ``data/taubench/`` and ``outputs/p1/``.
- Only sanitized aggregate summaries and SHA-256 fingerprints are written to tracked ``reports/``.
- Paid calls require explicit ``--run --cap-usd`` and checkpoint every row atomically under ``runs/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.analysis import cluster_interval  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.cache import make_key  # noqa: E402
from trajjudge.calibration import (  # noqa: E402
    average_precision,
    binary_metrics,
    exact_mcnemar,
    pr_curve_fail,
    recall_at_fpr,
    roc_curve_fail,
)
from trajjudge.config import load_provider_settings  # noqa: E402
from trajjudge.grounded_judge import (  # noqa: E402
    ABLATION_MODES,
    GRADER_NAME,
    PASS_THRESHOLD,
    PROMPT_VARIANTS,
    build_audit_messages,
    extract_evidence_ledger,
    grade_trajectory_grounded,
)
from trajjudge.judging import JudgeConfig, latest_rows, load_rows, openjudge_commit, rule_row, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.scenario_stats import ALL_THRESHOLDS, holm  # noqa: E402
from trajjudge.taubench_adapter import (  # noqa: E402
    AdaptedTauTrace,
    load_taubench_file,
    select_best_of_n_tasks,
    select_taubench_cohort,
)
from trajjudge.usage import budget_cost, load_pricing, load_reservations, utc_now  # noqa: E402

DATA_DIR = root / "data/taubench"
OUT_DIR = root / "outputs/p1"
COHORT_PATH = OUT_DIR / "taubench_cohort.json"
BON4_PATH = OUT_DIR / "taubench_bon4.json"
RULES_PATH = OUT_DIR / "p1-rule-baselines.jsonl"

DEFAULT_SOURCES: tuple[tuple[str, str | None], ...] = (
    ("DeepSeek-V3.2-Exp-thinking-off.jsonl", None),
    ("gpt-4o-airline.json", "gpt-4o"),
    ("gpt-4o-retail.json", "gpt-4o"),
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_balanced_cohort(
    *,
    per_agent_failures: int = 50,
    per_agent_passes: int = 50,
    seed: int = 20261119,
) -> dict[str, Any]:
    """Build a 200-trace cohort balanced across 2 agent vendors (50/50 fail/pass each) & both domains."""
    all_traces: list[AdaptedTauTrace] = []
    sources_meta: list[dict[str, Any]] = []
    for fname, default_model in DEFAULT_SOURCES:
        fpath = DATA_DIR / fname
        if not fpath.is_file():
            raise FileNotFoundError(f"missing τ-bench source file: {fpath}")
        loaded = load_taubench_file(fpath, default_agent_model=default_model)
        sources_meta.append({
            "file": fname,
            "sha256": _file_sha256(fpath),
            "n_records": len(loaded),
            "n_failures": sum(not t.objective_pass for t in loaded),
            "n_passes": sum(t.objective_pass for t in loaded),
            "n_scenarios": len({t.scenario_id for t in loaded}),
        })
        all_traces.extend(loaded)

    by_agent: dict[str, list[AdaptedTauTrace]] = defaultdict(list)
    for t in all_traces:
        by_agent[t.agent_model].append(t)

    selected: list[AdaptedTauTrace] = []
    for idx, (agent_name, agent_traces) in enumerate(sorted(by_agent.items())):
        sub = select_taubench_cohort(
            agent_traces,
            target_failures=per_agent_failures,
            target_passes=per_agent_passes,
            min_scenarios=30,
            seed=seed + idx,
        )
        selected.extend(sub["traces"])

    selected = sorted(selected, key=lambda x: x.trace_id)
    unique_scenarios = sorted({t.scenario_id for t in selected})
    cohort_sha = hashlib.sha256(json.dumps([t.trace_id for t in selected]).encode("utf-8")).hexdigest()

    # Best-of-4 tasks from gpt-4o (all 165 tasks have 4 trials)
    gpt4o_traces = by_agent.get("gpt-4o", [])
    bon4_tasks = select_best_of_n_tasks(gpt4o_traces, n_candidates=4, max_tasks=165)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cohort_payload = {
        "schema": 1,
        "generated_at": utc_now(),
        "seed": seed,
        "cohort_sha256": cohort_sha,
        "sources": sources_meta,
        "traces": [asdict(t) for t in selected],
    }
    atomic_text(COHORT_PATH, json.dumps(cohort_payload, ensure_ascii=False) + "\n")

    bon_by_id = {t.trace_id: asdict(t) for t in gpt4o_traces}
    bon_payload = {
        "schema": 1,
        "generated_at": utc_now(),
        "agent_model": "gpt-4o",
        "n_tasks": len(bon4_tasks),
        "n_mixed": sum(1 for x in bon4_tasks if x["mixed_outcomes"]),
        "oracle_pass_rate": round(sum(1 for x in bon4_tasks if x["oracle_pass"]) / len(bon4_tasks), 4) if bon4_tasks else None,
        "tasks": bon4_tasks,
        "traces_by_id": {tid: bon_by_id[tid] for task in bon4_tasks for tid in task["candidate_trace_ids"]},
    }
    atomic_text(BON4_PATH, json.dumps(bon_payload, ensure_ascii=False) + "\n")

    # Run deterministic rule baselines for free
    commit = openjudge_commit()
    rule_rows: list[dict[str, Any]] = []
    for t in selected:
        for rname in ("action_loop_detection", "observation_information_gain"):
            rule_rows.append(rule_row(t.trace_id, t.messages, rname, commit))
    atomic_text(RULES_PATH, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rule_rows))

    summary = {
        "generated_at": utc_now(),
        "seed": seed,
        "cohort_sha256": cohort_sha,
        "n_total": len(selected),
        "n_failures": sum(not t.objective_pass for t in selected),
        "n_passes": sum(t.objective_pass for t in selected),
        "n_scenarios": len(unique_scenarios),
        "meets_prereg_v3_target": (
            sum(not t.objective_pass for t in selected) >= 100 and len(unique_scenarios) >= 60
        ),
        "by_domain": dict(sorted(Counter(t.domain for t in selected).items())),
        "by_agent_model": dict(sorted(Counter(t.agent_model for t in selected).items())),
        "by_agent_and_outcome": {
            f"{k[0]}|{'pass' if k[1] else 'fail'}": v
            for k, v in sorted(Counter((t.agent_model, t.objective_pass) for t in selected).items())
        },
        "avg_messages": round(statistics.fmean(t.metadata["total_messages"] for t in selected), 1),
        "avg_tool_calls": round(statistics.fmean(t.metadata["total_tool_calls"] for t in selected), 1),
        "avg_mutating_calls": round(statistics.fmean(t.metadata["mutating_tool_calls"] for t in selected), 1),
        "best_of_4_pool": {
            "n_tasks": len(bon4_tasks),
            "n_mixed": sum(1 for x in bon4_tasks if x["mixed_outcomes"]),
            "random_expected_pass_rate": round(
                statistics.fmean(x["pass_count"] / x["n_candidates"] for x in bon4_tasks), 4
            ) if bon4_tasks else None,
            "oracle_pass_rate": bon_payload["oracle_pass_rate"],
        },
        "sources": sources_meta,
    }
    atomic_text(root / "reports/p1_cohort_summary.json", json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    return summary


def load_cohort() -> list[dict[str, Any]]:
    if not COHORT_PATH.is_file():
        raise FileNotFoundError(f"run `scripts/run_p1_taubench.py build` first ({COHORT_PATH} missing)")
    return json.loads(COHORT_PATH.read_text(encoding="utf-8"))["traces"]


def _apply_budget_guard(settings: Any, run_dir: Path, cap_usd: float) -> Any:
    run_dir.mkdir(parents=True, exist_ok=True)
    bpath = run_dir / "budget.json"
    if bpath.exists():
        saved = json.loads(bpath.read_text(encoding="utf-8"))
        if saved["stage_cap_usd"] != cap_usd:
            raise ValueError(f"resume must preserve original stage_cap_usd ({saved['stage_cap_usd']})")
    else:
        before = budget_cost(
            LLMClient(settings).usage_log.read(),
            load_pricing(settings.pricing_file),
            load_reservations(settings.usage_log),
        )
        if before is None:
            raise ValueError("historical spend unknown; reconcile usage log first")
        saved = {
            "stage_cap_usd": cap_usd,
            "spent_before_usd": before,
            "ceiling_usd": round(before + cap_usd, 6),
            "basis": "conservative peak guard plus reservations; not invoice",
        }
        atomic_text(bpath, json.dumps(saved, indent=2))
    return replace(settings, budget_usd=saved["ceiling_usd"])


def estimate_run_cost(traces: Sequence[Mapping[str, Any]], graders: Sequence[str], price: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    total_exp = 0.0
    total_guard = 0.0
    for g in graders:
        if g == GRADER_NAME:
            in_chars = sum(
                sum(len(m["content"]) for m in build_audit_messages(extract_evidence_ledger(t["messages"])))
                for t in traces
            )
            out_tok_exp = 320
            out_cap = 1280
        elif g == "trajectory_comprehensive":
            in_chars = sum(len(json.dumps(t["messages"], ensure_ascii=False)) + 2000 for t in traces)
            out_tok_exp = 520
            out_cap = 3072
        else:
            in_chars = sum(len(json.dumps(t["messages"], ensure_ascii=False)) + 1200 for t in traces)
            out_tok_exp = 140
            out_cap = 1024
        est_in_tok = in_chars / 3.6
        exp_usd = (est_in_tok * price.input_per_mtok + len(traces) * out_tok_exp * price.output_per_mtok) / 1_000_000
        guard_usd = ((in_chars + 4096 * len(traces)) * price.input_per_mtok + len(traces) * out_cap * price.output_per_mtok) / 1_000_000
        total_exp += exp_usd
        total_guard += guard_usd
        out[g] = {
            "n_calls": len(traces),
            "expected_peak_miss_usd": round(exp_usd, 4),
            "expected_with_cache_usd": round(exp_usd * 0.55, 4),
            "single_attempt_byte_guard_usd": round(guard_usd, 4),
        }
    return {
        "n_traces": len(traces),
        "by_grader": out,
        "total_expected_peak_miss_usd": round(total_exp, 4),
        "total_expected_with_cache_usd": round(total_exp * 0.55, 4),
        "total_single_attempt_byte_guard_usd": round(total_guard, 4),
    }


def _run_grounded_batch(
    traces: Sequence[Mapping[str, Any]],
    client: LLMClient,
    output: Path,
    run_dir: Path,
    *,
    phase: str,
    ablation: str,
    prompt_variant: str,
    workers: int = 4,
) -> dict[str, int]:
    from concurrent.futures import ThreadPoolExecutor
    import threading

    commit = openjudge_commit()
    descriptors = [{
        "trace_id": t["trace_id"],
        "grader": GRADER_NAME,
        "ablation": ablation,
        "prompt_variant": prompt_variant,
        "variant": "original",
        "repeat_id": 0,
        "input_sha256": make_key({"messages": t["messages"]}),
        "max_tokens": 1280,
    } for t in traces]
    keys = [make_key(d) for d in descriptors]
    plan = {
        "schema": 1,
        "phase": phase,
        "grader": GRADER_NAME,
        "provider": client.settings.provider,
        "model": client.settings.judge_model,
        "base_url": client.settings.base_url,
        "ablation": ablation,
        "prompt_variant": prompt_variant,
        "openjudge_commit": commit,
        "jobs": sorted(descriptors, key=make_key),
    }
    identity = make_key(plan)
    run_dir.mkdir(parents=True, exist_ok=True)
    active = run_dir / "active.lock"
    try:
        fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"active.lock exists in {run_dir}") from None
    os.close(fd)
    try:
        mpath = run_dir / "manifest.json"
        if mpath.exists():
            saved = json.loads(mpath.read_text(encoding="utf-8"))
            if saved["identity"] != identity:
                raise ValueError("manifest identity mismatch; use a fresh run_id")
        stored: dict[str, dict[str, Any]] = {}
        for k in keys:
            rpath = run_dir / "rows" / f"{k}.json"
            if rpath.exists():
                stored[k] = json.loads(rpath.read_text(encoding="utf-8"))

        def checkpoint() -> None:
            atomic_text(output, "".join(json.dumps(stored[k], ensure_ascii=False) + "\n" for k in keys if k in stored))
            done = [k for k in keys if k in stored and stored[k]["status"] == "ok"]
            atomic_text(mpath, json.dumps({
                "identity": identity, "plan": plan, "total_jobs": len(traces),
                "completed": done, "updated_at": utc_now(),
            }, indent=2))

        checkpoint()
        lock, stop = threading.Lock(), threading.Event()
        counts = {"run": 0, "skipped": 0, "error": 0, "stopped_early": 0}
        todo = []
        for k, tr in zip(keys, traces):
            if k in stored and stored[k]["status"] == "ok":
                counts["skipped"] += 1
            else:
                todo.append((k, tr))

        def work(item: tuple[str, Mapping[str, Any]]) -> None:
            k, tr = item
            if stop.is_set():
                return
            row = grade_trajectory_grounded(
                tr["trace_id"], tr["messages"], client,
                repeat_id=0, variant="original", phase=phase,
                commit=commit, ablation=ablation, prompt_variant=prompt_variant,
            )
            row["job_id"] = k
            row["provider"] = client.settings.provider
            with lock:
                atomic_text(run_dir / "rows" / f"{k}.json", json.dumps(row, ensure_ascii=False))
                stored[k] = row
                checkpoint()
                counts["run"] += 1
                if row["status"] != "ok":
                    counts["error"] += 1
            if row.get("fatal"):
                stop.set()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, todo))
        counts["stopped_early"] = int(stop.is_set())
        return counts
    finally:
        active.unlink(missing_ok=True)


def evaluate_p1_reports(*, resamples: int = 2000, seed: int = 0) -> dict[str, Any]:
    """Aggregate all completed P1 JSONL files against objective τ-bench DB labels."""
    cohort = load_cohort()
    by_tid = {t["trace_id"]: t for t in cohort}
    rater_files = sorted(OUT_DIR.glob("p1-*.jsonl"))

    raters_out: dict[str, Any] = {}
    preds_by_rater: dict[str, dict[str, bool]] = {}

    for path in rater_files:
        rows = latest_rows(load_rows(path))
        # Group by (label_key) in case a file has multiple graders (e.g. rule baselines)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            g = str(r.get("grader"))
            model = str(r.get("judge_model") or "rule")
            ab = r.get("ablation")
            pv = r.get("prompt_variant")
            suffix = "" if (not ab or (ab == "full" and pv == "v0")) else f"|{ab}|{pv}"
            key = f"{path.stem}:{g}|{model}{suffix}" if path.name == RULES_PATH.name else f"{path.stem}"
            grouped[key].append(r)

        for rater_key, r_rows in sorted(grouped.items()):
            valid_rows = [r for r in r_rows if r.get("status") == "ok" and r["trace_id"] in by_tid]
            error_rows = [r for r in r_rows if r.get("status") != "ok" and r["trace_id"] in by_tid]
            if not valid_rows:
                continue
            grader_name = str(valid_rows[0]["grader"])
            threshold = ALL_THRESHOLDS.get(grader_name, 0.50)

            items = []
            for r in sorted(valid_rows, key=lambda x: x["trace_id"]):
                tr = by_tid[r["trace_id"]]
                sc = float(r["score"])
                items.append({
                    "trace_id": r["trace_id"],
                    "scenario_id": tr["scenario_id"],
                    "domain": tr["domain"],
                    "agent_model": tr["agent_model"],
                    "truth": bool(tr["objective_pass"]),
                    "score": sc,
                    "pred": sc >= threshold,
                })
            preds_by_rater[rater_key] = {x["trace_id"]: x["pred"] for x in items}
            truth = [x["truth"] for x in items]
            scores = [x["score"] for x in items]
            pred = [x["pred"] for x in items]
            units = [x["scenario_id"] for x in items]
            bm = binary_metrics(truth, pred)
            n_fail = sum(not h for h in truth)
            n_pass = sum(truth)
            caught = sum((not h) and (not p) for h, p in zip(truth, pred))
            false_kills = sum(h and (not p) for h, p in zip(truth, pred))

            at_fpr = {}
            for target in (0.10, 0.20):
                pt = recall_at_fpr(truth, scores, target)
                at_fpr[f"fpr_{int(round(target * 100))}"] = {
                    "recall_step": round(pt["step"], 4) if pt["step"] is not None else None,
                    "recall_interpolated": round(pt["interpolated"], 4) if pt["interpolated"] is not None else None,
                    "recall_interpolated_ci": cluster_interval(
                        items, units,
                        lambda d, t=target: recall_at_fpr([x["truth"] for x in d], [x["score"] for x in d], t)["interpolated"],
                        resamples=resamples, seed=seed,
                    ),
                }

            # Domain and Agent-family breakdown (self-preference audit!)
            by_agent_metrics = {}
            for am in sorted({x["agent_model"] for x in items}):
                sub = [x for x in items if x["agent_model"] == am]
                st, sp, ss = [x["truth"] for x in sub], [x["pred"] for x in sub], [x["score"] for x in sub]
                nf = sum(not v for v in st)
                np_ = sum(st)
                by_agent_metrics[am] = {
                    "n": len(sub),
                    "failure_recall": round(sum((not a) and (not b) for a, b in zip(st, sp)) / nf, 4) if nf else None,
                    "false_kill_rate": round(sum(a and (not b) for a, b in zip(st, sp)) / np_, 4) if np_ else None,
                    "roc_auc": round(m.auc(st, ss), 4) if m.auc(st, ss) is not None else None,
                    "pr_auc_fail": round(average_precision([not v for v in st], [-s for s in ss]), 4)
                    if average_precision([not v for v in st], [-s for s in ss]) is not None else None,
                }

            veto_overrode = sum(1 for r in valid_rows if (r.get("audit") or {}).get("veto_overrode_model"))
            unauth = sum(1 for r in valid_rows if (r.get("audit") or {}).get("unauthorized_side_effect"))
            prompt_toks = sum((r.get("usage") or {}).get("prompt_tokens", 0) for r in valid_rows)
            comp_toks = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in valid_rows)

            raters_out[rater_key] = {
                "grader": grader_name,
                "judge_model": valid_rows[0].get("judge_model"),
                "n_valid": len(valid_rows),
                "n_errors": len(error_rows),
                "format_error_rate": round(len(error_rows) / (len(valid_rows) + len(error_rows)), 4),
                "n_scenarios": len(set(units)),
                "n_fail": n_fail,
                "n_pass": n_pass,
                "default_threshold": threshold,
                "caught_failures": f"{caught}/{n_fail}",
                "failure_recall": round(caught / n_fail, 4) if n_fail else None,
                "false_kills": f"{false_kills}/{n_pass}",
                "false_kill_rate": round(false_kills / n_pass, 4) if n_pass else None,
                "balanced_accuracy": round(bm["balanced_accuracy"], 4) if bm["balanced_accuracy"] is not None else None,
                "kappa": round(bm["kappa"], 4) if bm["kappa"] is not None else None,
                "kappa_ci": cluster_interval(
                    items, units, lambda d: m.cohen_kappa([x["truth"] for x in d], [x["pred"] for x in d]),
                    resamples=resamples, seed=seed,
                ),
                "roc_auc": round(m.auc(truth, scores), 4) if m.auc(truth, scores) is not None else None,
                "roc_auc_ci": cluster_interval(
                    items, units, lambda d: m.auc([x["truth"] for x in d], [x["score"] for x in d]),
                    resamples=resamples, seed=seed,
                ),
                "pr_auc_fail": round(average_precision([not h for h in truth], [-s for s in scores]), 4)
                if average_precision([not h for h in truth], [-s for s in scores]) is not None else None,
                "pr_auc_fail_ci": cluster_interval(
                    items, units, lambda d: average_precision([not x["truth"] for x in d], [-x["score"] for x in d]),
                    resamples=resamples, seed=seed,
                ),
                "recall_at_fpr": at_fpr,
                "by_agent_model": by_agent_metrics,
                "veto_overrode_model_count": veto_overrode,
                "unauthorized_side_effect_count": unauth,
                "total_prompt_tokens": prompt_toks,
                "total_completion_tokens": comp_toks,
                "roc_curve": roc_curve_fail(truth, scores),
                "pr_curve": pr_curve_fail(truth, scores),
            }

    # Pairwise Exact McNemar across all non-rule LLM raters with >= 100 common traces
    llm_keys = sorted(k for k, v in raters_out.items() if v["judge_model"] and v["n_valid"] >= 20)
    mcnemar_pairs: dict[str, Any] = {}
    p_map: dict[str, float | None] = {}
    for i, ka in enumerate(llm_keys):
        for kb in llm_keys[i + 1 :]:
            common = sorted(set(preds_by_rater[ka]) & set(preds_by_rater[kb]))
            if not common:
                continue
            truth = [bool(by_tid[t]["objective_pass"]) for t in common]
            pa = [preds_by_rater[ka][t] for t in common]
            pb = [preds_by_rater[kb][t] for t in common]
            fm = exact_mcnemar(truth, pa, pb, fail_only=True)
            om = exact_mcnemar(truth, pa, pb, fail_only=False)
            pname = f"{kb}_vs_{ka}"
            mcnemar_pairs[pname] = {
                "n_common": len(common),
                "fail_recall_mcnemar": fm,
                "overall_accuracy_mcnemar": om,
            }
            p_map[pname] = fm["exact_p"]

    report = {
        "generated_at": utc_now(),
        "cohort_n": len(cohort),
        "raters": raters_out,
        "mcnemar_pairs": mcnemar_pairs,
        "holm_fail_recall": holm(p_map) if p_map else None,
    }
    out_path = root / "reports/p1_taubench_eval.json"
    atomic_text(out_path, json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "estimate", "run", "report"))
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--graders", nargs="+", default=["trajectory_comprehensive", "trajectory_accuracy", GRADER_NAME])
    parser.add_argument("--ablation", default="full", choices=ABLATION_MODES)
    parser.add_argument("--prompt-variant", default="v0", choices=PROMPT_VARIANTS)
    parser.add_argument("--limit", type=int, default=0, help="Optional prefix limit for small pilot checks (0 = all 200)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--run-prefix", default="p1")
    args = parser.parse_args(argv)

    if args.action == "build":
        summary = build_balanced_cohort()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.action == "report":
        rep = evaluate_p1_reports()
        print(json.dumps({
            "cohort_n": rep["cohort_n"],
            "raters": {
                k: {
                    "n_valid": v["n_valid"], "n_errors": v["n_errors"],
                    "caught": v["caught_failures"], "fk": v["false_kills"],
                    "roc_auc": v["roc_auc"], "pr_auc": v["pr_auc_fail"],
                    "r10": v["recall_at_fpr"]["fpr_10"]["recall_interpolated"],
                    "r20": v["recall_at_fpr"]["fpr_20"]["recall_interpolated"],
                    "veto_overrides": v["veto_overrode_model_count"],
                }
                for k, v in rep["raters"].items()
            },
        }, ensure_ascii=False, indent=2))
        return 0

    traces = load_cohort()
    if args.limit > 0:
        traces = traces[: args.limit]

    settings = load_provider_settings(args.provider, require_key=(args.action == "run" and not args.offline))
    prices = load_pricing(settings.pricing_file)
    price = prices.get(settings.judge_model)
    if price is None:
        raise ValueError(f"no verified price for {settings.judge_model!r} in {settings.pricing_file} (see D5)")

    est = estimate_run_cost(traces, args.graders, price)
    if args.action == "estimate":
        print(json.dumps({"provider": args.provider, "model": settings.judge_model, **est}, indent=2))
        return 0

    if not args.offline and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("run requires a positive --cap-usd (or --offline)")

    for g in args.graders:
        suffix = "" if (g != GRADER_NAME or (args.ablation == "full" and args.prompt_variant == "v0")) else f"-{args.ablation}-{args.prompt_variant}"
        lim_tag = f"-n{len(traces)}" if args.limit > 0 else ""
        run_id = f"{args.run_prefix}-{args.provider}-{g.replace('trajectory_', '')}{suffix}{lim_tag}"
        run_dir = root / "runs" / run_id
        out_jsonl = OUT_DIR / f"{run_id}.jsonl"
        run_settings = _apply_budget_guard(settings, run_dir, args.cap_usd) if not args.offline else settings
        client = LLMClient(run_settings, offline=args.offline, max_attempts=2, timeout=120.0)
        if g == GRADER_NAME:
            counts = _run_grounded_batch(
                traces, client, out_jsonl, run_dir,
                phase=args.run_prefix, ablation=args.ablation,
                prompt_variant=args.prompt_variant, workers=args.workers,
            )
        else:
            cfg = JudgeConfig(g, False, "direct", 1, defended=False)
            jobs = [(t["trace_id"], t["messages"], cfg, 0, "original") for t in traces]
            counts = run_jobs(jobs, client, out_jsonl, workers=args.workers, run_dir=run_dir, phase=args.run_prefix, schema_retries=1)
        print(json.dumps({"run_id": run_id, "grader": g, **counts}))
        if counts.get("stopped_early"):
            break

    evaluate_p1_reports()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
