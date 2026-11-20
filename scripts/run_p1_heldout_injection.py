#!/usr/bin/env python
"""P1-5 Held-Out Indirect Prompt-Injection Runner & Analyzer (PREREG_v3 §5).

Evaluates ``trajectory_comprehensive``, ``trajectory_accuracy``, and ``evidence_grounded``
(plus ``ablation=no_quarantine``) against the SHA-256-frozen 15-template held-out test suite
in ``trajjudge.perturb_v3`` across 3 locations (``tool_result``, ``assistant_mid``, ``assistant_final``),
paired with a 3-repeat unperturbed noise floor on the exact same trajectories.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.analysis import _valid, cluster_interval  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.config import load_provider_settings  # noqa: E402
from trajjudge.grounded_judge import GRADER_NAME, grade_trajectory_grounded  # noqa: E402
from trajjudge.judging import JudgeConfig, latest_rows, load_rows, openjudge_commit, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.perturb_v3 import (  # noqa: E402
    HELD_OUT_TEST_TEMPLATES,
    LOCATIONS_V3,
    held_out_suite_sha256,
    inject_v3,
)
from trajjudge.scenario_stats import ALL_THRESHOLDS, MIN_SCENARIOS, injection_metrics_v3, normalized_delta  # noqa: E402
from trajjudge.usage import load_pricing, utc_now  # noqa: E402

import importlib.util  # noqa: E402

OUT_DIR = root / "outputs/p1_injection"


def _load_p1_driver():
    spec = importlib.util.spec_from_file_location("run_p1_taubench", root / "scripts/run_p1_taubench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def select_fail_subset(cohort: Sequence[Mapping[str, Any]], n_fail: int) -> list[dict[str, Any]]:
    """Deterministically pick ``n_fail`` objective failures maximizing unique scenarios and agent balance."""
    fails = [t for t in cohort if not t["objective_pass"]]
    seen_scen: set[str] = set()
    chosen: list[dict[str, Any]] = []
    # First pass: 1 per scenario, alternating agent models
    by_agent: dict[str, list[dict[str, Any]]] = {}
    for t in sorted(fails, key=lambda x: (x["scenario_id"], x["trace_id"])):
        by_agent.setdefault(t["agent_model"], []).append(t)
    agents = sorted(by_agent)
    idx = 0
    while len(chosen) < n_fail:
        progressed = False
        for ag in agents:
            while by_agent[ag]:
                cand = by_agent[ag].pop(0)
                if cand["scenario_id"] not in seen_scen or idx > 0:
                    seen_scen.add(cand["scenario_id"])
                    chosen.append(cand)
                    progressed = True
                    break
            if len(chosen) >= n_fail:
                break
        if not progressed:
            break
        idx += 1
    return sorted(chosen, key=lambda x: x["trace_id"])


def plan_heldout_variants(
    traces: Sequence[Mapping[str, Any]],
    *,
    templates: Sequence[str],
    locations: Sequence[str],
    compact_secondary_templates: Sequence[str] | None = None,
) -> list[tuple[str, list[dict[str, Any]], str, int]]:
    """Build (trace_id, messages, variant, repeat_id) list: 3 unperturbed repeats + held-out injections.

    When ``compact_secondary_templates`` is set, applies ALL ``templates`` to ``tool_result``
    and applies ``compact_secondary_templates`` to ``assistant_mid`` and ``assistant_final``.
    """
    items: list[tuple[str, list[dict[str, Any]], str, int]] = []
    for t in traces:
        # 3 unperturbed repeats for exact P0-3 noise floor on the same cohort
        for r in range(3):
            items.append((t["trace_id"], t["messages"], "original", r))
        for loc in locations:
            tpl_list = (
                compact_secondary_templates
                if (compact_secondary_templates is not None and loc != "tool_result")
                else templates
            )
            for tpl_id in tpl_list:
                try:
                    pert, _ = inject_v3(t["messages"], tpl_id, loc)
                except ValueError:
                    continue
                items.append((t["trace_id"], pert, f"{tpl_id}/{loc}", 0))
    return items


def _bucket_stats(items: Sequence[Mapping[str, Any]], *, resamples: int = 2000, seed: int = 0) -> dict[str, Any]:
    if not items:
        return {"n_valid_pairs": 0}
    units = [x["scenario_id"] for x in items]
    bf = [x for x in items if x["base_fail"]]
    bf_units = [x["scenario_id"] for x in bf]
    bf_scens = len(set(bf_units))
    f2p = sum(x["fail_to_pass"] for x in bf)
    p2f = sum(x["pass_to_fail"] for x in items)
    inf = sum(x["inflated"] for x in items)
    return {
        "n_valid_pairs": len(items),
        "n_traces": len({x["trace_id"] for x in items}),
        "n_scenarios": len(set(units)),
        "base_fail_pairs": len(bf),
        "base_fail_scenarios": bf_scens,
        "fail_to_pass_count": f2p,
        "pass_to_fail_count": p2f,
        "decision_flip_case_study": bf_scens < MIN_SCENARIOS,
        "decision_flip_rate": round(f2p / len(bf), 4) if bf else None,
        "decision_flip_rate_ci": (
            cluster_interval(bf, bf_units, lambda d: sum(x["fail_to_pass"] for x in d) / len(d), resamples=resamples, seed=seed)
            if bf else None
        ),
        "mean_norm_delta": round(statistics.fmean(x["norm_delta"] for x in items), 4),
        "mean_norm_delta_ci": cluster_interval(
            items, units, lambda d: statistics.fmean(x["norm_delta"] for x in d), resamples=resamples, seed=seed,
        ),
        "score_inflation_count": inf,
        "score_inflation_rate": round(inf / len(items), 4),
    }


def compute_p15_arm_summary(
    rows: Sequence[Mapping[str, Any]],
    clusters: Mapping[str, str],
    noise_floors: Mapping[str, Any],
) -> dict[str, Any]:
    """Aggregate P1-5 held-out results per (grader, defended) across overall, location, and category."""
    tpl_cat = {t.template_id: t.category for t in HELD_OUT_TEST_TEMPLATES}
    originals = {
        (row["grader"], row.get("defended", False), row.get("judge_model"), row["trace_id"], row.get("repeat_id", 0)): row
        for row in rows if row.get("variant", "original") == "original"
    }
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts_by_arm: dict[str, dict[str, int]] = defaultdict(lambda: {"ok": 0, "error": 0, "unpaired": 0})

    for row in rows:
        arm_key = f"{row['grader']}|defended={row.get('defended', False)}"
        if row.get("variant", "original") == "original":
            counts_by_arm[arm_key]["ok" if _valid(row) else "error"] += 1
            continue
        counts_by_arm[arm_key]["ok" if _valid(row) else "error"] += 1
        key = (row["grader"], row.get("defended", False), row.get("judge_model"), row["trace_id"], row.get("repeat_id", 0))
        base = originals.get(key)
        if base is None or not _valid(base) or not _valid(row):
            counts_by_arm[arm_key]["unpaired"] += 1
            continue
        grader = str(row["grader"])
        thresh = ALL_THRESHOLDS.get(grader)
        o_sc, p_sc = float(base["score"]), float(row["score"])
        base_fail = thresh is not None and o_sc < thresh
        now_fail = thresh is not None and p_sc < thresh
        variant = str(row["variant"])
        tpl_id, loc = variant.split("/", 1) if "/" in variant else (variant, "unknown")
        tid = str(row["trace_id"])
        by_arm[arm_key].append({
            "trace_id": tid,
            "scenario_id": clusters.get(tid, tid),
            "location": loc,
            "category": tpl_cat.get(tpl_id, "other"),
            "template_id": tpl_id,
            "norm_delta": normalized_delta(grader, p_sc - o_sc),
            "inflated": p_sc > o_sc,
            "base_fail": bool(base_fail),
            "fail_to_pass": bool(base_fail and not now_fail),
            "pass_to_fail": bool(thresh is not None and not base_fail and now_fail),
        })

    out: dict[str, Any] = {}
    for arm_key in sorted(set(by_arm) | set(counts_by_arm)):
        items = by_arm.get(arm_key, [])
        by_loc = {loc: _bucket_stats([x for x in items if x["location"] == loc]) for loc in sorted({x["location"] for x in items})}
        by_cat = {cat: _bucket_stats([x for x in items if x["category"] == cat]) for cat in sorted({x["category"] for x in items})}
        out[arm_key] = {
            "row_counts": dict(counts_by_arm[arm_key]),
            "noise_floor": noise_floors.get(arm_key),
            "overall": _bucket_stats(items),
            "by_location": by_loc,
            "by_category": by_cat,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("estimate", "run", "report"))
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--n-fail", type=int, default=24)
    parser.add_argument("--templates", nargs="*", default=[t.template_id for t in HELD_OUT_TEST_TEMPLATES])
    parser.add_argument("--locations", nargs="*", default=list(LOCATIONS_V3))
    parser.add_argument("--compact-locations", action="store_true", help="All templates on tool_result; 4 cross-category templates on assistant_mid/assistant_final")
    parser.add_argument("--graders", nargs="+", default=["trajectory_comprehensive", GRADER_NAME])
    parser.add_argument("--ablation", default="full", choices=("full", "no_quarantine"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    drv = _load_p1_driver()
    cohort = drv.load_cohort()
    fail_traces = select_fail_subset(cohort, args.n_fail)
    trace_scenarios = {t["trace_id"]: t["scenario_id"] for t in cohort}
    secondary = ("T01_qa_signoff", "T05_zh_qa_pass", "T09_json_grader_note", "T13_spoof_user_confirm") if args.compact_locations else None
    items = plan_heldout_variants(fail_traces, templates=args.templates, locations=args.locations, compact_secondary_templates=secondary)

    if args.action == "report":
        all_rows: list[dict[str, Any]] = []
        if OUT_DIR.is_dir():
            for p in sorted(OUT_DIR.glob("p15-*.jsonl")):
                all_rows.extend(latest_rows(load_rows(p)))
        res_v3 = injection_metrics_v3(all_rows, trace_scenarios)
        rep = {
            "generated_at": utc_now(),
            "held_out_suite_sha256": held_out_suite_sha256(),
            "n_fail_traces": len(fail_traces),
            "n_scenarios": len({t["scenario_id"] for t in fail_traces}),
            "arm_summary": compute_p15_arm_summary(all_rows, trace_scenarios, res_v3.get("noise_floors") or {}),
            "results": res_v3,
        }
        out_path = root / "reports/p15_heldout_injection.json"
        atomic_text(out_path, json.dumps(rep, ensure_ascii=False, indent=1) + "\n")
        print(f"written: {out_path.relative_to(root)}")
        return 0

    settings = load_provider_settings(args.provider, require_key=(args.action == "run" and not args.offline))
    price = load_pricing(settings.pricing_file).get(settings.judge_model)
    if price is None:
        raise ValueError(f"no verified price for {settings.judge_model!r}")

    est_calls = len(items) * len(args.graders)
    est_usd = est_calls * (5000 * price.input_per_mtok + 350 * price.output_per_mtok) / 1_000_000
    if args.action == "estimate":
        print(json.dumps({
            "held_out_suite_sha256": held_out_suite_sha256(),
            "n_fail_traces": len(fail_traces),
            "n_scenarios": len({t["scenario_id"] for t in fail_traces}),
            "templates": len(args.templates),
            "locations": list(args.locations),
            "items_per_grader": len(items),
            "total_calls": est_calls,
            "expected_peak_miss_usd": round(est_usd, 4),
            "expected_with_cache_usd": round(est_usd * 0.45, 4),
        }, indent=2))
        return 0

    if not args.offline and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("run requires a positive --cap-usd")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    commit = openjudge_commit()
    for g in args.graders:
        tag_ab = "" if (g != GRADER_NAME or args.ablation == "full") else f"-{args.ablation}"
        run_id = f"p15-{args.provider}-{g.replace('trajectory_', '')}{tag_ab}-f{len(fail_traces)}"
        run_dir = root / "runs" / run_id
        out_jsonl = OUT_DIR / f"{run_id}.jsonl"
        run_settings = drv._apply_budget_guard(settings, run_dir, args.cap_usd) if not args.offline else settings
        client = LLMClient(run_settings, offline=args.offline, max_attempts=4, backoff_base=2.0, timeout=120.0)
        if g == GRADER_NAME:
            from concurrent.futures import ThreadPoolExecutor
            import threading
            from trajjudge.cache import make_key

            run_dir.mkdir(parents=True, exist_ok=True)
            rows_dir = run_dir / "rows"
            rows_dir.mkdir(parents=True, exist_ok=True)
            stored: dict[str, dict[str, Any]] = {}
            keys = []
            for tid, msgs, var, rep_id in items:
                k = make_key({"tid": tid, "var": var, "rep": rep_id, "ab": args.ablation, "model": settings.judge_model})
                keys.append(k)
                rp = rows_dir / f"{k}.json"
                if rp.exists():
                    stored[k] = json.loads(rp.read_text(encoding="utf-8"))

            lock, stop = threading.Lock(), threading.Event()
            counts = {"run": 0, "skipped": 0, "error": 0, "stopped_early": 0}
            todo = []
            for k, it in zip(keys, items):
                if k in stored and stored[k]["status"] == "ok":
                    counts["skipped"] += 1
                else:
                    todo.append((k, it))

            def work(pair):
                k, (tid, msgs, var, rep_id) = pair
                if stop.is_set():
                    return
                row = grade_trajectory_grounded(
                    tid, msgs, client, repeat_id=rep_id, variant=var,
                    phase="p15", max_tokens=args.max_tokens or 2048, commit=commit, ablation=args.ablation,
                    schema_retries=1,
                )
                row["job_id"] = k
                with lock:
                    atomic_text(rows_dir / f"{k}.json", json.dumps(row, ensure_ascii=False))
                    stored[k] = row
                    atomic_text(out_jsonl, "".join(json.dumps(stored[kk], ensure_ascii=False) + "\n" for kk in keys if kk in stored))
                    counts["run"] += 1
                    counts["error"] += int(row["status"] != "ok")
                if row.get("fatal"):
                    stop.set()

            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                list(pool.map(work, todo))
            counts["stopped_early"] = int(stop.is_set())
        else:
            cfg = JudgeConfig(g, False, "direct", 1, max_tokens=args.max_tokens, defended=False)
            jobs = [(tid, msgs, cfg, rep_id, var) for tid, msgs, var, rep_id in items]
            counts = run_jobs(jobs, client, out_jsonl, workers=args.workers, run_dir=run_dir, phase="p15", schema_retries=1)
        print(json.dumps({"run_id": run_id, **counts}))
        if counts.get("stopped_early"):
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
