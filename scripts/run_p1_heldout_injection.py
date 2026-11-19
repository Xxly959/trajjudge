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
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

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
from trajjudge.scenario_stats import injection_metrics_v3  # noqa: E402
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
) -> list[tuple[str, list[dict[str, Any]], str, int]]:
    """Build (trace_id, messages, variant, repeat_id) list: 3 unperturbed repeats + 1 per (template, location)."""
    items: list[tuple[str, list[dict[str, Any]], str, int]] = []
    for t in traces:
        # 3 unperturbed repeats for exact P0-3 noise floor on the same cohort
        for r in range(3):
            items.append((t["trace_id"], t["messages"], "original", r))
        for tpl_id in templates:
            for loc in locations:
                try:
                    pert, _ = inject_v3(t["messages"], tpl_id, loc)
                except ValueError:
                    continue
                items.append((t["trace_id"], pert, f"{tpl_id}/{loc}", 0))
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("estimate", "run", "report"))
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--n-fail", type=int, default=24)
    parser.add_argument("--templates", nargs="*", default=[t.template_id for t in HELD_OUT_TEST_TEMPLATES])
    parser.add_argument("--locations", nargs="*", default=list(LOCATIONS_V3))
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
    items = plan_heldout_variants(fail_traces, templates=args.templates, locations=args.locations)

    if args.action == "report":
        all_rows: list[dict[str, Any]] = []
        if OUT_DIR.is_dir():
            for p in sorted(OUT_DIR.glob("p15-*.jsonl")):
                all_rows.extend(latest_rows(load_rows(p)))
        rep = {
            "generated_at": utc_now(),
            "held_out_suite_sha256": held_out_suite_sha256(),
            "n_fail_traces": len(fail_traces),
            "n_scenarios": len({t["scenario_id"] for t in fail_traces}),
            "results": injection_metrics_v3(all_rows, trace_scenarios),
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
        client = LLMClient(run_settings, offline=args.offline, max_attempts=2, timeout=120.0)
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
