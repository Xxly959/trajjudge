#!/usr/bin/env python
"""Independent Validation Set (n=100) for Roadmap v3 Module B (PREREG_v3 §9).

Samples 100 unseen trajectories from the 825-trace tau-bench pool after excluding:
- all 200 traces in the main cohort (outputs/p1/taubench_cohort.json);
- all 200 traces used in P2-A Best-of-4 t50 (outputs/p2_bon/p2bon-*.jsonl).

Under the pool constraint (DeepSeek-V3.2 has only 10 unused failures left; p2bon-t50
consumed all 50 gpt-4o-airline tasks), draws 10 fail + 10 pass from DeepSeek-V3.2
and 40 fail + 40 pass from gpt-4o (retail domain), prioritizing scenarios never seen
in the main cohort and annotating every trace with ``scenario_seen: bool``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.taubench_adapter import AdaptedTauTrace, load_taubench_file  # noqa: E402

DATA_DIR = root / "data/taubench"
MAIN_COHORT_PATH = root / "outputs/p1/taubench_cohort.json"
BON_DIR = root / "outputs/p2_bon"
VAL_DIR = root / "outputs/p1_val"
VAL_COHORT_PATH = VAL_DIR / "taubench_val_v3.json"
VAL_SUMMARY_PATH = root / "reports/p1_validation_cohort_summary.json"
VAL_REPORT_PATH = root / "reports/p1_validation_v3.json"

DEFAULT_SOURCES: tuple[tuple[str, str | None], ...] = (
    ("DeepSeek-V3.2-Exp-thinking-off.jsonl", None),
    ("gpt-4o-airline.json", "gpt-4o"),
    ("gpt-4o-retail.json", "gpt-4o"),
)

VALIDATION_GRADERS = ("evidence_grounded", "trajectory_accuracy", "trajectory_comprehensive")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_script_mod(name: str, rel_path: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, root / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _round_robin_bucket(
    candidates: Sequence[AdaptedTauTrace],
    target: int,
    *,
    seen_scenarios: set[str],
    seed: int,
) -> list[dict[str, Any]]:
    """Select ``target`` traces, exhausting unseen scenarios round-robin before seen scenarios."""
    rng = random.Random(seed)
    unseen_by_sc: dict[str, list[AdaptedTauTrace]] = defaultdict(list)
    seen_by_sc: dict[str, list[AdaptedTauTrace]] = defaultdict(list)
    for tr in sorted(candidates, key=lambda x: (x.scenario_id, x.trial, x.trace_id)):
        if tr.scenario_id in seen_scenarios:
            seen_by_sc[tr.scenario_id].append(tr)
        else:
            unseen_by_sc[tr.scenario_id].append(tr)

    def _drain(by_sc: dict[str, list[AdaptedTauTrace]], need: int) -> list[AdaptedTauTrace]:
        scens = sorted(by_sc)
        rng.shuffle(scens)
        buckets = {s: list(by_sc[s]) for s in scens}
        for s in scens:
            rng.shuffle(buckets[s])
        chosen: list[AdaptedTauTrace] = []
        while len(chosen) < need:
            added = False
            for s in scens:
                if buckets[s] and len(chosen) < need:
                    chosen.append(buckets[s].pop(0))
                    added = True
            if not added:
                break
        return chosen

    picked_unseen = _drain(unseen_by_sc, target)
    picked_seen = _drain(seen_by_sc, target - len(picked_unseen)) if len(picked_unseen) < target else []
    combined = picked_unseen + picked_seen
    if len(combined) != target:
        raise RuntimeError(f"bucket insufficient: needed {target}, got {len(combined)}")
    out: list[dict[str, Any]] = []
    for tr in combined:
        d = asdict(tr)
        d["scenario_seen"] = tr.scenario_id in seen_scenarios
        out.append(d)
    return out


def build_validation_cohort(*, seed: int = 20261120) -> dict[str, Any]:
    """Deterministically build the 100-trace independent validation cohort."""
    main_cohort = json.loads(MAIN_COHORT_PATH.read_text(encoding="utf-8"))["traces"]
    main_ids = {t["trace_id"] for t in main_cohort}
    main_scenarios = {t["scenario_id"] for t in main_cohort}

    bon_ids: set[str] = set()
    for fn in sorted(BON_DIR.glob("p2bon-*.jsonl")):
        for line in fn.read_text(encoding="utf-8").splitlines():
            if line.strip():
                bon_ids.add(json.loads(line)["trace_id"])

    all_traces: list[AdaptedTauTrace] = []
    for fname, default_model in DEFAULT_SOURCES:
        all_traces.extend(load_taubench_file(DATA_DIR / fname, default_agent_model=default_model))

    excluded = main_ids | bon_ids
    pool = [t for t in all_traces if t.trace_id not in excluded]

    bucket_specs = [
        ("deepseek-ai/DeepSeek-V3.2-Exp-thinking-off", False, 10),
        ("deepseek-ai/DeepSeek-V3.2-Exp-thinking-off", True, 10),
        ("gpt-4o", False, 40),
        ("gpt-4o", True, 40),
    ]
    selected: list[dict[str, Any]] = []
    for idx, (agent_model, obj_pass, quota) in enumerate(bucket_specs):
        sub = [t for t in pool if t.agent_model == agent_model and t.objective_pass is obj_pass]
        selected.extend(
            _round_robin_bucket(sub, quota, seen_scenarios=main_scenarios, seed=seed + idx * 17)
        )

    selected = sorted(selected, key=lambda x: str(x["trace_id"]))
    assert len(selected) == 100
    assert not ({t["trace_id"] for t in selected} & excluded)

    cohort_sha = hashlib.sha256(
        json.dumps([t["trace_id"] for t in selected]).encode("utf-8")
    ).hexdigest()

    VAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "generated_at": _utc_now(),
        "seed": seed,
        "cohort_sha256": cohort_sha,
        "excluded_main_n": len(main_ids),
        "excluded_bon_n": len(bon_ids),
        "remaining_pool_n": len(pool),
        "traces": selected,
    }
    atomic_text(VAL_COHORT_PATH, json.dumps(payload, ensure_ascii=False) + "\n")

    unseen_traces = [t for t in selected if not t["scenario_seen"]]
    seen_traces = [t for t in selected if t["scenario_seen"]]
    summary = {
        "generated_at": payload["generated_at"],
        "seed": seed,
        "cohort_sha256": cohort_sha,
        "source_pool_total": len(all_traces),
        "excluded_main_n": len(main_ids),
        "excluded_bon_union_n": len(excluded),
        "remaining_pool_n": len(pool),
        "n_total": len(selected),
        "n_failures": sum(not t["objective_pass"] for t in selected),
        "n_passes": sum(t["objective_pass"] for t in selected),
        "n_scenarios": len({t["scenario_id"] for t in selected}),
        "scenario_seen_split": {
            "unseen": {
                "n_traces": len(unseen_traces),
                "n_failures": sum(not t["objective_pass"] for t in unseen_traces),
                "n_passes": sum(t["objective_pass"] for t in unseen_traces),
                "n_scenarios": len({t["scenario_id"] for t in unseen_traces}),
            },
            "seen": {
                "n_traces": len(seen_traces),
                "n_failures": sum(not t["objective_pass"] for t in seen_traces),
                "n_passes": sum(t["objective_pass"] for t in seen_traces),
                "n_scenarios": len({t["scenario_id"] for t in seen_traces}),
            },
        },
        "by_domain": dict(sorted(Counter(t["domain"] for t in selected).items())),
        "by_agent_and_outcome": {
            f"{k[0]}|{'pass' if k[1] else 'fail'}": v
            for k, v in sorted(Counter((t["agent_model"], t["objective_pass"]) for t in selected).items())
        },
        "pool_constraint_note": (
            "DeepSeek-V3.2 has only 10 unused failures remaining after the 200-trace main cohort, "
            "and p2bon-t50 consumed all 50 gpt-4o-airline tasks; therefore the 100-trace validation cohort "
            "balances 50/50 pass/fail within each agent (DeepSeek 10+10, GPT-4o 40+40 retail) and "
            "exhausts unseen scenarios first."
        ),
    }
    atomic_text(VAL_SUMMARY_PATH, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def load_val_cohort() -> list[dict[str, Any]]:
    if not VAL_COHORT_PATH.is_file():
        raise FileNotFoundError(f"run `scripts/run_p1_validation.py build` first ({VAL_COHORT_PATH} missing)")
    return json.loads(VAL_COHORT_PATH.read_text(encoding="utf-8"))["traces"]


def _eval_subset_metrics(
    traces: Sequence[Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    grader: str,
    *,
    itt: bool = False,
    resamples: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    from trajjudge import metrics as m
    from trajjudge.analysis import cluster_interval
    from trajjudge.calibration import average_precision, binary_metrics, recall_at_fpr
    from trajjudge.scenario_stats import ALL_THRESHOLDS

    pa = _load_script_mod("paired_auc", "scripts/paired_auc.py")
    thr = ALL_THRESHOLDS.get(grader, 0.50)

    items = []
    n_valid = 0
    n_err = 0
    for tr in sorted(traces, key=lambda x: str(x["trace_id"])):
        tid = str(tr["trace_id"])
        row = rows.get(tid)
        ok = (
            row is not None
            and row.get("status") == "ok"
            and type(row.get("score")) in (int, float)
            and math.isfinite(float(row["score"]))
        )
        if ok:
            n_valid += 1
            sc = float(row["score"])  # type: ignore[index]
        else:
            n_err += 1
            if not itt:
                continue
            sc = 0.0
        items.append({
            "trace_id": tid,
            "scenario_id": tr["scenario_id"],
            "truth": bool(tr["objective_pass"]),
            "score": sc,
            "pred": sc >= thr,
        })
    if not items:
        return {"n_eval": 0, "status": "empty"}

    truth = [x["truth"] for x in items]
    scores = [x["score"] for x in items]
    pred = [x["pred"] for x in items]
    units = [x["scenario_id"] for x in items]
    bm = binary_metrics(truth, pred)
    n_fail = sum(not h for h in truth)
    n_pass = sum(truth)
    caught = sum((not h) and (not p) for h, p in zip(truth, pred))
    fk = sum(h and (not p) for h, p in zip(truth, pred))
    fail_scores = [pa.row_to_fail_score(rows.get(x["trace_id"]), grader, itt=itt) for x in items]
    auc_val = pa.roc_auc_fail([not h for h in truth], fail_scores)
    pr_val = average_precision([not h for h in truth], [-s for s in scores])

    return {
        "mode": "itt" if itt else "complete_case",
        "n_candidates": len(traces),
        "n_eval": len(items),
        "n_valid_ok": n_valid,
        "n_errors": n_err,
        "invalid_rate": round(n_err / len(traces), 4) if traces else 0.0,
        "n_scenarios": len(set(units)),
        "n_fail": n_fail,
        "n_pass": n_pass,
        "default_threshold": thr,
        "caught_failures": f"{caught}/{n_fail}",
        "failure_recall": round(caught / n_fail, 4) if n_fail else None,
        "false_kills": f"{fk}/{n_pass}",
        "false_kill_rate": round(fk / n_pass, 4) if n_pass else None,
        "kappa": round(bm["kappa"], 4) if bm["kappa"] is not None else None,
        "kappa_ci": cluster_interval(
            items, units, lambda d: m.cohen_kappa([x["truth"] for x in d], [x["pred"] for x in d]),
            resamples=resamples, seed=seed,
        ),
        "roc_auc": round(auc_val, 4) if auc_val is not None else None,
        "roc_auc_ci": cluster_interval(
            items, units,
            lambda d: pa.roc_auc_fail([not x["truth"] for x in d], [-x["score"] for x in d]),
            resamples=resamples, seed=seed,
        ),
        "pr_auc_fail": round(pr_val, 4) if pr_val is not None else None,
        "recall_at_fpr": {
            "fpr_10_interp": round(recall_at_fpr(truth, scores, 0.10)["interpolated"], 4)
            if recall_at_fpr(truth, scores, 0.10)["interpolated"] is not None else None,
            "fpr_20_interp": round(recall_at_fpr(truth, scores, 0.20)["interpolated"], 4)
            if recall_at_fpr(truth, scores, 0.20)["interpolated"] is not None else None,
        },
    }


def _domain_shift_diagnostic(
    main_traces: Sequence[Mapping[str, Any]],
    val_traces: Sequence[Mapping[str, Any]],
    val_rows: Mapping[str, Mapping[str, Mapping[str, Any]]],
    pa: Any,
) -> dict[str, Any]:
    from trajjudge.scenario_stats import ALL_THRESHOLDS

    def _slice_stats(traces: Sequence[Mapping[str, Any]], rows: Mapping[str, Mapping[str, Any]], grader: str) -> dict[str, Any]:
        thr = ALL_THRESHOLDS.get(grader, 0.50)
        ok_rows = []
        for tr in traces:
            r = rows.get(str(tr["trace_id"]))
            if r is not None and r.get("status") == "ok" and type(r.get("score")) in (int, float) and math.isfinite(float(r["score"])):
                ok_rows.append((tr, r, float(r["score"])))
        if not ok_rows:
            return {"n_valid": 0}
        y_fail = [not bool(tr["objective_pass"]) for tr, _, _ in ok_rows]
        fail_scores = [pa.row_to_fail_score(r, grader, itt=False) for _, r, _ in ok_rows]
        auc_v = pa.roc_auc_fail(y_fail, fail_scores)
        nf = sum(y_fail)
        np_ = len(ok_rows) - nf
        caught = sum(yf and sc < thr for yf, (_, _, sc) in zip(y_fail, ok_rows))
        fk = sum((not yf) and sc < thr for yf, (_, _, sc) in zip(y_fail, ok_rows))
        ctoks = [(r.get("usage") or {}).get("completion_tokens", 0) for _, r, _ in ok_rows]
        return {
            "n_valid": len(ok_rows),
            "n_fail": nf,
            "n_pass": np_,
            "roc_auc": round(auc_v, 4) if auc_v is not None else None,
            "failure_recall": round(caught / nf, 4) if nf else None,
            "false_kill_rate": round(fk / np_, 4) if np_ else None,
            "avg_completion_tokens": round(sum(ctoks) / len(ctoks), 1),
        }

    main_run_dirs = {
        "evidence_grounded": root / "runs/p1-hubcore_glm_flash-evidence_grounded",
        "trajectory_accuracy": root / "runs/p1-hubcore_glm_flash-accuracy",
        "trajectory_comprehensive": root / "runs/p1-hubcore_glm_flash-comprehensive",
    }
    main_rows = {g: pa.load_run_rows_by_trace(rd) for g, rd in main_run_dirs.items()}
    main_by_dom: dict[str, dict[str, Any]] = {}
    for dom in ("airline", "retail"):
        sub = [t for t in main_traces if t["domain"] == dom]
        main_by_dom[dom] = {g: _slice_stats(sub, main_rows[g], g) for g in VALIDATION_GRADERS}

    val_retail = [t for t in val_traces if t["domain"] == "retail"]
    val_by_dom = {
        "retail": {g: _slice_stats(val_retail, val_rows[g], g) for g in VALIDATION_GRADERS},
        "all": {g: _slice_stats(val_traces, val_rows[g], g) for g in VALIDATION_GRADERS},
    }
    return {"main_cohort": main_by_dom, "validation_cohort": val_by_dom}


def _reasoning_confounder_diagnostic() -> dict[str, Any]:
    cache_root = root / ".cache/llm"
    stats: dict[tuple[str, str], dict[str, int]] = {}
    if cache_root.is_dir():
        for cf in sorted(cache_root.rglob("*.json")):
            try:
                d = json.loads(cf.read_text(encoding="utf-8"))
            except Exception:
                continue
            tag = str(d.get("tag") or "")
            if not (tag.startswith("p1/") or tag.startswith("p1val/")):
                continue
            if d.get("model") != "glm-5.3-flash":
                continue
            prefix = tag.split("/")[0]
            if "evidence_grounded" in tag:
                g = "evidence_grounded"
            elif "accuracy" in tag:
                g = "trajectory_accuracy"
            elif "comprehensive" in tag:
                g = "trajectory_comprehensive"
            else:
                continue
            k = (prefix, g)
            s = stats.setdefault(k, {"n": 0, "has_reasoning": 0, "completion_tokens": 0})
            s["n"] += 1
            if d.get("reasoning_content"):
                s["has_reasoning"] += 1
            s["completion_tokens"] += int(d.get("completion_tokens") or 0)
    out: dict[str, dict[str, Any]] = {"p1_main": {}, "p1val": {}}
    for (prefix, g), s in sorted(stats.items()):
        target = "p1_main" if prefix == "p1" else "p1val"
        n = s["n"]
        out[target][g] = {
            "n_cached_calls": n,
            "has_reasoning_rate": round(s["has_reasoning"] / n, 4) if n else None,
            "avg_completion_tokens": round(s["completion_tokens"] / n, 1) if n else None,
        }
    return out


def evaluate_validation_report(*, provider: str = "hubcore_glm_flash", resamples: int = 2000, seed: int = 0) -> dict[str, Any]:
    """Compute validation metrics, paired ΔAUC, ITT sensitivity, and scenario_seen stratification."""
    traces = load_val_cohort()
    main_traces = json.loads(MAIN_COHORT_PATH.read_text(encoding="utf-8"))["traces"]
    pa = _load_script_mod("paired_auc", "scripts/paired_auc.py")

    run_dirs = {
        g: root / "runs" / f"p1val-{provider}-{g.replace('trajectory_', '')}"
        for g in VALIDATION_GRADERS
    }
    loaded_rows = {g: pa.load_run_rows_by_trace(rd) for g, rd in run_dirs.items()}

    raters_out: dict[str, Any] = {}
    for g in VALIDATION_GRADERS:
        rows = loaded_rows[g]
        unseen_tr = [t for t in traces if not t["scenario_seen"]]
        seen_tr = [t for t in traces if t["scenario_seen"]]
        raters_out[g] = {
            "run_dir": run_dirs[g].name,
            "complete_case": _eval_subset_metrics(traces, rows, g, itt=False, resamples=resamples, seed=seed),
            "itt": _eval_subset_metrics(traces, rows, g, itt=True, resamples=resamples, seed=seed),
            "by_scenario_seen": {
                "unseen_complete": _eval_subset_metrics(unseen_tr, rows, g, itt=False, resamples=resamples, seed=seed),
                "unseen_itt": _eval_subset_metrics(unseen_tr, rows, g, itt=True, resamples=resamples, seed=seed),
                "seen_complete": _eval_subset_metrics(seen_tr, rows, g, itt=False, resamples=resamples, seed=seed),
                "seen_itt": _eval_subset_metrics(seen_tr, rows, g, itt=True, resamples=resamples, seed=seed),
            },
        }

    unseen_ids = {t["trace_id"] for t in traces if not t["scenario_seen"]}
    seen_ids = {t["trace_id"] for t in traces if t["scenario_seen"]}

    def _pair_block(ga: str, gb: str) -> dict[str, Any]:
        return {
            "all_complete_case": pa.compute_paired_delta_auc(
                traces, loaded_rows[ga], loaded_rows[gb], grader_a=ga, grader_b=gb,
                mode="complete_case", resamples=resamples, seed=seed,
            ),
            "all_itt": pa.compute_paired_delta_auc(
                traces, loaded_rows[ga], loaded_rows[gb], grader_a=ga, grader_b=gb,
                mode="itt", resamples=resamples, seed=seed,
            ),
            "unseen_complete_case": pa.compute_paired_delta_auc(
                traces, loaded_rows[ga], loaded_rows[gb], grader_a=ga, grader_b=gb,
                mode="complete_case", resamples=resamples, seed=seed, subset_trace_ids=unseen_ids,
            ),
            "unseen_itt": pa.compute_paired_delta_auc(
                traces, loaded_rows[ga], loaded_rows[gb], grader_a=ga, grader_b=gb,
                mode="itt", resamples=resamples, seed=seed, subset_trace_ids=unseen_ids,
            ),
            "seen_complete_case": pa.compute_paired_delta_auc(
                traces, loaded_rows[ga], loaded_rows[gb], grader_a=ga, grader_b=gb,
                mode="complete_case", resamples=resamples, seed=seed, subset_trace_ids=seen_ids,
            ),
            "seen_itt": pa.compute_paired_delta_auc(
                traces, loaded_rows[ga], loaded_rows[gb], grader_a=ga, grader_b=gb,
                mode="itt", resamples=resamples, seed=seed, subset_trace_ids=seen_ids,
            ),
        }

    paired = {
        "grounded_vs_comprehensive": _pair_block("evidence_grounded", "trajectory_comprehensive"),
        "grounded_vs_accuracy": _pair_block("evidence_grounded", "trajectory_accuracy"),
        "accuracy_vs_comprehensive": _pair_block("trajectory_accuracy", "trajectory_comprehensive"),
    }

    prim_cc = paired["grounded_vs_comprehensive"]["all_complete_case"]
    prim_itt = paired["grounded_vs_comprehensive"]["all_itt"]
    primary_supported_cc = bool(
        prim_cc["delta_auc"] is not None
        and prim_cc["delta_auc"] > 0
        and prim_cc["ci_95"]
        and prim_cc["ci_95"][0] > 0
    )
    primary_supported_itt = bool(
        prim_itt["delta_auc"] is not None
        and prim_itt["delta_auc"] > 0
        and prim_itt["ci_95"]
        and prim_itt["ci_95"][0] > 0
    )

    report = {
        "generated_at": _utc_now(),
        "provider": provider,
        "cohort_n": len(traces),
        "primary_hypothesis_check": {
            "hypothesis": "Grounded-GLMFlash ΔAUC > Comprehensive-GLMFlash with 95% cluster CI excluding 0",
            "supported_complete_case": primary_supported_cc,
            "supported_itt": primary_supported_itt,
        },
        "raters": raters_out,
        "paired_delta_auc": paired,
        "domain_shift_diagnostic": _domain_shift_diagnostic(main_traces, traces, loaded_rows, pa),
        "reasoning_confounder_diagnostic": _reasoning_confounder_diagnostic(),
    }
    atomic_text(VAL_REPORT_PATH, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "estimate", "run", "report"))
    parser.add_argument("--provider", default="hubcore_glm_flash")
    parser.add_argument("--graders", nargs="+", default=list(VALIDATION_GRADERS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--schema-retries", type=int, default=2)
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    if args.action == "build":
        summary = build_validation_cohort()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.action == "report":
        rep = evaluate_validation_report(provider=args.provider)
        compact = {
            "cohort_n": rep["cohort_n"],
            "primary_hypothesis_check": rep["primary_hypothesis_check"],
            "raters": {
                g: {
                    "cc": (v["complete_case"]["n_eval"], v["complete_case"]["roc_auc"], v["complete_case"]["caught_failures"], v["complete_case"]["false_kills"]),
                    "itt": (v["itt"]["n_eval"], v["itt"]["roc_auc"], v["itt"]["caught_failures"], v["itt"]["false_kills"]),
                }
                for g, v in rep["raters"].items()
            },
            "paired_delta_auc": {
                k: {
                    sub: (v[sub]["delta_auc"], v[sub]["ci_95"], v[sub]["p_value"], v[sub]["n_paired"])
                    for sub in ("all_complete_case", "all_itt", "unseen_complete_case", "seen_complete_case")
                }
                for k, v in rep["paired_delta_auc"].items()
            },
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        return 0

    from trajjudge.config import load_provider_settings
    from trajjudge.grounded_judge import GRADER_NAME, extract_evidence_ledger
    from trajjudge.judging import JudgeConfig, openjudge_commit, run_jobs
    from trajjudge.llm import LLMClient
    from trajjudge.usage import load_pricing

    p1_mod = _load_script_mod("run_p1_taubench", "scripts/run_p1_taubench.py")
    traces = load_val_cohort()
    settings = load_provider_settings(args.provider, require_key=(args.action == "run" and not args.offline))
    prices = load_pricing(settings.pricing_file)
    price = prices.get(settings.judge_model)
    if price is None:
        raise ValueError(f"no verified price for {settings.judge_model!r} in {settings.pricing_file}")

    est = p1_mod.estimate_run_cost(traces, args.graders, price)
    if args.action == "estimate":
        print(json.dumps({"provider": args.provider, "model": settings.judge_model, **est}, indent=2))
        return 0

    if not args.offline and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("run requires a positive --cap-usd (or --offline)")

    # Run grounded with schema_retries=2 & max_tokens=4096; openjudge graders with schema_retries=2 & max_tokens=4096
    from trajjudge.grounded_judge import grade_trajectory_grounded
    from trajjudge.cache import make_key
    from trajjudge.usage import utc_now
    from concurrent.futures import ThreadPoolExecutor
    import os
    import threading

    for g in args.graders:
        run_id = f"p1val-{args.provider}-{g.replace('trajectory_', '')}"
        run_dir = root / "runs" / run_id
        out_jsonl = VAL_DIR / f"{run_id}.jsonl"
        run_settings = p1_mod._apply_budget_guard(settings, run_dir, args.cap_usd) if not args.offline else settings
        client = LLMClient(run_settings, offline=args.offline, max_attempts=4, timeout=120.0)
        if g == GRADER_NAME:
            commit = openjudge_commit()
            descriptors = [{
                "trace_id": t["trace_id"],
                "grader": GRADER_NAME,
                "ablation": "full",
                "prompt_variant": "v0",
                "variant": "original",
                "repeat_id": 0,
                "input_sha256": make_key({"messages": t["messages"]}),
                "max_tokens": args.max_tokens,
                "schema_retries": args.schema_retries,
            } for t in traces]
            keys = [make_key(d) for d in descriptors]
            plan = {
                "schema": 1,
                "phase": "p1val",
                "grader": GRADER_NAME,
                "provider": client.settings.provider,
                "model": client.settings.judge_model,
                "base_url": client.settings.base_url,
                "ablation": "full",
                "prompt_variant": "v0",
                "schema_retries": args.schema_retries,
                "openjudge_commit": commit,
                "jobs": sorted(descriptors, key=make_key),
            }
            identity = make_key(plan)
            run_dir.mkdir(parents=True, exist_ok=True)
            active = run_dir / "active.lock"
            fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
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
                    atomic_text(out_jsonl, "".join(json.dumps(stored[k], ensure_ascii=False) + "\n" for k in keys if k in stored))
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
                        repeat_id=0, variant="original", phase="p1val",
                        max_tokens=args.max_tokens,
                        commit=commit, ablation="full", prompt_variant="v0",
                        schema_retries=args.schema_retries,
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

                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    list(pool.map(work, todo))
                counts["stopped_early"] = int(stop.is_set())
            finally:
                active.unlink(missing_ok=True)
        else:
            cfg = JudgeConfig(g, False, "direct", 1, max_tokens=args.max_tokens, defended=False)
            jobs = [(t["trace_id"], t["messages"], cfg, 0, "original") for t in traces]
            counts = run_jobs(
                jobs, client, out_jsonl, workers=args.workers, run_dir=run_dir,
                phase="p1val", schema_retries=args.schema_retries,
            )
        print(json.dumps({"run_id": run_id, "grader": g, **counts}))
        if counts.get("stopped_early"):
            break

    evaluate_validation_report(provider=args.provider)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
