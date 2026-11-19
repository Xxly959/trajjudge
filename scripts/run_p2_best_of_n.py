#!/usr/bin/env python
"""P2-A Best-of-N Reranking (N=4) on τ-bench multi-trial tasks (PREREG_v3 §7).

Compares 5 candidate selection strategies across 50-100 τ-bench tasks (each with N=4 trials):
1. ``random``: exact expected pass rate ``mean(pass_count / 4)``;
2. ``final_confidence``: surface-fluency / decisive final-reply heuristic (no tool verification);
3. ``comprehensive``: argmax OpenJudge ``TrajectoryComprehensiveGrader`` score;
4. ``grounded``: argmax ``EvidenceGroundedGrader`` score;
5. ``oracle``: executable DB-state verification upper bound (``pass_count > 0``).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.analysis import cluster_interval  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.calibration import exact_mcnemar  # noqa: E402
from trajjudge.config import load_provider_settings  # noqa: E402
from trajjudge.grounded_judge import GRADER_NAME  # noqa: E402
from trajjudge.judging import JudgeConfig, latest_rows, load_rows, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.usage import load_pricing, utc_now  # noqa: E402

BON4_PATH = root / "outputs/p1/taubench_bon4.json"
OUT_DIR = root / "outputs/p2_bon"

_CONFIDENT_RE = re.compile(
    r"\b(completed|confirmed|successfully|done|processed|cancelled|updated|booked|exchanged|refunded|all set)\b",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"\b(sorry|unable|cannot|can't|couldn't|error|failed|not possible|unfortunately|transfer)\b",
    re.IGNORECASE,
)


def _load_p1_driver():
    spec = importlib.util.spec_from_file_location("run_p1_taubench", root / "scripts/run_p1_taubench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def final_turn_confidence_score(messages: Sequence[Mapping[str, Any]]) -> float:
    """Deterministic surface-fluency / final-reply confidence heuristic (baseline 2)."""
    last_asst = next(
        (str(m.get("content") or "") for m in reversed(messages) if m.get("role") == "assistant" and str(m.get("content") or "").strip()),
        "",
    )
    if not last_asst:
        return 0.0
    pos = len(_CONFIDENT_RE.findall(last_asst))
    neg = len(_HEDGE_RE.findall(last_asst))
    length_bonus = min(len(last_asst), 600) / 600.0
    return round(0.50 + 0.15 * pos - 0.15 * neg + 0.10 * length_bonus, 4)


def load_bon_subset(n_tasks: int) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not BON4_PATH.is_file():
        raise FileNotFoundError(f"run `scripts/run_p1_taubench.py build` first ({BON4_PATH} missing)")
    data = json.loads(BON4_PATH.read_text(encoding="utf-8"))
    tasks = data["tasks"][:n_tasks]
    traces_by_id = data["traces_by_id"]
    return tasks, traces_by_id


def analyze_best_of_n(
    tasks: Sequence[Mapping[str, Any]],
    traces_by_id: Mapping[str, Mapping[str, Any]],
    score_maps: Mapping[str, Mapping[str, float]],
    *,
    resamples: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    """Compute selected pass rates, cluster 95% CIs, and paired McNemar tests across all 5 selectors."""
    per_task: list[dict[str, Any]] = []
    for task in tasks:
        cids = list(task["candidate_trace_ids"])
        cands = [traces_by_id[cid] for cid in cids]
        row: dict[str, Any] = {
            "scenario_id": task["scenario_id"],
            "n_candidates": len(cands),
            "random": sum(bool(c["objective_pass"]) for c in cands) / len(cands),
            "oracle": 1.0 if any(bool(c["objective_pass"]) for c in cands) else 0.0,
        }
        # Final-turn confidence selector
        conf_best = max(cands, key=lambda c: final_turn_confidence_score(c["messages"]))
        row["final_confidence"] = 1.0 if conf_best["objective_pass"] else 0.0

        # Judge-based selectors (only evaluated on tasks where all 4 candidates have valid scores)
        for sel_name, smap in score_maps.items():
            if all(cid in smap for cid in cids):
                best = max(cands, key=lambda c: smap[c["trace_id"]])
                row[sel_name] = 1.0 if best["objective_pass"] else 0.0
            else:
                row[sel_name] = None
        per_task.append(row)

    selectors = ["random", "final_confidence", *sorted(score_maps.keys()), "oracle"]
    summary: dict[str, Any] = {}
    for sel in selectors:
        valid = [r for r in per_task if r.get(sel) is not None]
        if not valid:
            continue
        units = [r["scenario_id"] for r in valid]
        rate = statistics.fmean(float(r[sel]) for r in valid)
        summary[sel] = {
            "n_tasks": len(valid),
            "pass_rate": round(rate, 4),
            "pass_rate_ci": cluster_interval(
                valid, units, lambda d, k=sel: statistics.fmean(float(x[k]) for x in d),
                resamples=resamples, seed=seed,
            ),
        }

    # Paired McNemar among deterministic binary selectors (excluding continuous random expectation)
    binary_sels = [s for s in ("final_confidence", *sorted(score_maps.keys())) if s in summary]
    mcnemar: dict[str, Any] = {}
    for i, sa in enumerate(binary_sels):
        for sb in binary_sels[i + 1 :]:
            common = [r for r in per_task if r.get(sa) is not None and r.get(sb) is not None]
            if not common:
                continue
            truth = [True] * len(common)
            pa = [bool(r[sa] >= 0.5) for r in common]
            pb = [bool(r[sb] >= 0.5) for r in common]
            mcnemar[f"{sb}_vs_{sa}"] = exact_mcnemar(truth, pa, pb, fail_only=False)

    return {
        "generated_at": utc_now(),
        "n_tasks_planned": len(tasks),
        "selectors": summary,
        "mcnemar_pass_rate": mcnemar,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("estimate", "run", "report"))
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--n-tasks", type=int, default=60)
    parser.add_argument("--graders", nargs="+", default=["trajectory_comprehensive", GRADER_NAME])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    drv = _load_p1_driver()
    tasks, traces_by_id = load_bon_subset(args.n_tasks)
    cand_traces = [traces_by_id[cid] for task in tasks for cid in task["candidate_trace_ids"]]

    if args.action == "report":
        score_maps: dict[str, dict[str, float]] = {}
        # Load scores from both P2 BoN outputs and P1 outputs (cache reuse!)
        for folder in (OUT_DIR, root / "outputs/p1"):
            if not folder.is_dir():
                continue
            for p in sorted(folder.glob("*.jsonl")):
                rows = latest_rows(load_rows(p))
                for r in rows:
                    if r.get("status") != "ok" or r.get("variant", "original") != "original":
                        continue
                    g = str(r.get("grader"))
                    if g not in ("trajectory_comprehensive", GRADER_NAME):
                        continue
                    key = f"{g}|{r.get('judge_model')}"
                    score_maps.setdefault(key, {})[str(r["trace_id"])] = float(r["score"])
        rep = analyze_best_of_n(tasks, traces_by_id, score_maps)
        out_path = root / "reports/p2_best_of_n.json"
        atomic_text(out_path, json.dumps(rep, ensure_ascii=False, indent=1) + "\n")
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    settings = load_provider_settings(args.provider, require_key=(args.action == "run" and not args.offline))
    price = load_pricing(settings.pricing_file).get(settings.judge_model)
    if price is None:
        raise ValueError(f"no verified price for {settings.judge_model!r}")

    est = drv.estimate_run_cost(cand_traces, args.graders, price)
    if args.action == "estimate":
        print(json.dumps({"n_tasks": len(tasks), "n_candidates": len(cand_traces), **est}, indent=2))
        return 0

    if not args.offline and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("run requires a positive --cap-usd")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for g in args.graders:
        run_id = f"p2bon-{args.provider}-{g.replace('trajectory_', '')}-t{len(tasks)}"
        run_dir = root / "runs" / run_id
        out_jsonl = OUT_DIR / f"{run_id}.jsonl"
        run_settings = drv._apply_budget_guard(settings, run_dir, args.cap_usd) if not args.offline else settings
        client = LLMClient(run_settings, offline=args.offline, max_attempts=2, timeout=120.0)
        if g == GRADER_NAME:
            counts = drv._run_grounded_batch(
                cand_traces, client, out_jsonl, run_dir,
                phase="p2bon", ablation="full", prompt_variant="v0", workers=args.workers,
            )
        else:
            cfg = JudgeConfig(g, False, "direct", 1, defended=False)
            jobs = [(t["trace_id"], t["messages"], cfg, 0, "original") for t in cand_traces]
            counts = run_jobs(jobs, client, out_jsonl, workers=args.workers, run_dir=run_dir, phase="p2bon", schema_retries=1)
        print(json.dumps({"run_id": run_id, **counts}))
        if counts.get("stopped_early"):
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
