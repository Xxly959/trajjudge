#!/usr/bin/env python
"""P1-6 Component Ablation (4 modes) and Prompt Sensitivity (3 variants) on τ-bench (PREREG_v3 §6).

Stratified 60-trace cohort (30 objective failures + 30 objective passes, balanced across agents):
- Ablation modes: ``full``, ``no_veto``, ``no_quarantine``, ``no_ledger``
- Prompt variants (in ``full`` mode): ``v0`` (reuses ``full``), ``v1``, ``v2``
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.calibration import average_precision, binary_metrics, recall_at_fpr  # noqa: E402
from trajjudge.config import load_provider_settings  # noqa: E402
from trajjudge.grounded_judge import ABLATION_MODES, GRADER_NAME, PASS_THRESHOLD, PROMPT_VARIANTS  # noqa: E402
from trajjudge.judging import latest_rows, load_rows  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.usage import load_pricing, utc_now  # noqa: E402

OUT_DIR = root / "outputs/p1_ablation"


def _load_p1_driver():
    spec = importlib.util.spec_from_file_location("run_p1_taubench", root / "scripts/run_p1_taubench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def select_ablation_subset(cohort: Sequence[Mapping[str, Any]], n_per_class: int = 30) -> list[dict[str, Any]]:
    """Deterministically pick ``n_per_class`` fails + ``n_per_class`` passes balanced across agent models."""
    chosen: list[dict[str, Any]] = []
    for outcome in (False, True):
        by_ag: dict[str, list[dict[str, Any]]] = {}
        for t in sorted(cohort, key=lambda x: (x["scenario_id"], x["trace_id"])):
            if bool(t["objective_pass"]) == outcome:
                by_ag.setdefault(t["agent_model"], []).append(dict(t))
        agents = sorted(by_ag)
        picked = 0
        while picked < n_per_class:
            progressed = False
            for ag in agents:
                if by_ag[ag] and picked < n_per_class:
                    chosen.append(by_ag[ag].pop(0))
                    picked += 1
                    progressed = True
            if not progressed:
                break
    return sorted(chosen, key=lambda x: x["trace_id"])


def summarize_rows(rows: Sequence[Mapping[str, Any]], by_tid: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("status") == "ok" and r["trace_id"] in by_tid]
    errs = [r for r in rows if r.get("status") != "ok" and r["trace_id"] in by_tid]
    if not ok:
        return {"n_valid": 0, "n_errors": len(errs)}
    truth = [bool(by_tid[r["trace_id"]]["objective_pass"]) for r in ok]
    scores = [float(r["score"]) for r in ok]
    pred = [s >= PASS_THRESHOLD for s in scores]
    bm = binary_metrics(truth, pred)
    n_fail = sum(not t for t in truth)
    n_pass = sum(truth)
    caught = sum((not t) and (not p) for t, p in zip(truth, pred))
    fk = sum(t and (not p) for t, p in zip(truth, pred))
    veto_over = sum(1 for r in ok if (r.get("audit") or {}).get("veto_overrode_model"))
    return {
        "n_valid": len(ok),
        "n_errors": len(errs),
        "n_scenarios": len({by_tid[r["trace_id"]]["scenario_id"] for r in ok}),
        "caught_failures": f"{caught}/{n_fail}",
        "failure_recall": round(caught / n_fail, 4) if n_fail else None,
        "false_kills": f"{fk}/{n_pass}",
        "false_kill_rate": round(fk / n_pass, 4) if n_pass else None,
        "balanced_accuracy": round(bm["balanced_accuracy"], 4) if bm["balanced_accuracy"] is not None else None,
        "kappa": round(bm["kappa"], 4) if bm["kappa"] is not None else None,
        "roc_auc": round(m.auc(truth, scores), 4) if m.auc(truth, scores) is not None else None,
        "pr_auc_fail": round(average_precision([not t for t in truth], [-s for s in scores]), 4)
        if average_precision([not t for t in truth], [-s for s in scores]) is not None else None,
        "recall_at_fpr_10": round(recall_at_fpr(truth, scores, 0.10)["interpolated"] or 0.0, 4),
        "recall_at_fpr_20": round(recall_at_fpr(truth, scores, 0.20)["interpolated"] or 0.0, 4),
        "veto_overrode_model_count": veto_over,
        "veto_overrode_model_rate": round(veto_over / len(ok), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("estimate", "run", "report"))
    parser.add_argument("--provider", default="hubcore_glm_flash")
    parser.add_argument("--n-per-class", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--only-prompt-variants", nargs="*", choices=PROMPT_VARIANTS, default=None,
                        help="Run only these prompt variants (ablation=full); report still summarizes all configs.")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)

    drv = _load_p1_driver()
    cohort = drv.load_cohort()
    subset = select_ablation_subset(cohort, n_per_class=args.n_per_class)
    by_tid = {t["trace_id"]: t for t in subset}

    # 4 ablations (full/v0, no_veto/v0, no_quarantine/v0, no_ledger/v0) + 2 extra prompt variants (full/v1, full/v2)
    configs = [(ab, "v0") for ab in ABLATION_MODES] + [("full", pv) for pv in PROMPT_VARIANTS if pv != "v0"]

    if args.action == "report":
        ablation_out: dict[str, Any] = {}
        prompt_out: dict[str, Any] = {}
        for ab, pv in configs:
            fname = OUT_DIR / f"p16-{args.provider}-{ab}-{pv}-n{len(subset)}.jsonl"
            if not fname.is_file():
                continue
            stats = summarize_rows(latest_rows(load_rows(fname)), by_tid)
            if pv == "v0":
                ablation_out[ab] = stats
            if ab == "full":
                prompt_out[pv] = stats

        # Compute prompt sensitivity variance across v0/v1/v2
        variance: dict[str, Any] = {}
        if len(prompt_out) >= 2:
            for metric in ("failure_recall", "false_kill_rate", "roc_auc", "pr_auc_fail", "recall_at_fpr_10"):
                vals = [v[metric] for v in prompt_out.values() if v.get(metric) is not None]
                if len(vals) >= 2:
                    variance[metric] = {
                        "mean": round(statistics.fmean(vals), 4),
                        "sd": round(statistics.stdev(vals), 4),
                        "min": round(min(vals), 4),
                        "max": round(max(vals), 4),
                    }
        rep = {
            "generated_at": utc_now(),
            "provider": args.provider,
            "n_subset": len(subset),
            "n_scenarios": len({t["scenario_id"] for t in subset}),
            "ablations": ablation_out,
            "prompt_variants": prompt_out,
            "prompt_sensitivity": variance,
        }
        out_path = root / "reports/p16_ablation.json"
        atomic_text(out_path, json.dumps(rep, ensure_ascii=False, indent=1) + "\n")
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    settings = load_provider_settings(args.provider, require_key=(args.action == "run" and not args.offline))
    price = load_pricing(settings.pricing_file).get(settings.judge_model)
    if price is None:
        raise ValueError(f"no verified price for {settings.judge_model!r}")

    if args.action == "estimate":
        total_calls = len(subset) * len(configs)
        est = total_calls * (5500 * price.input_per_mtok + 900 * price.output_per_mtok) / 1_000_000
        print(json.dumps({"n_subset": len(subset), "configs": configs, "total_calls": total_calls, "est_peak_usd": round(est, 4)}, indent=2))
        return 0

    if not args.offline and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("run requires a positive --cap-usd")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_configs = [("full", pv) for pv in args.only_prompt_variants] if args.only_prompt_variants else configs
    for ab, pv in run_configs:
        run_id = f"p16-{args.provider}-{ab}-{pv}-n{len(subset)}"
        run_dir = root / "runs" / run_id
        out_jsonl = OUT_DIR / f"{run_id}.jsonl"
        run_settings = drv._apply_budget_guard(settings, run_dir, args.cap_usd) if not args.offline else settings
        client = LLMClient(run_settings, offline=args.offline, max_attempts=4, backoff_base=2.0, timeout=120.0)
        counts = drv._run_grounded_batch(
            subset, client, out_jsonl, run_dir,
            phase="p16", ablation=ab, prompt_variant=pv,
            workers=args.workers, max_tokens=args.max_tokens,
        )
        print(json.dumps({"run_id": run_id, **counts}))
        if counts.get("stopped_early"):
            break

    return main(["report", "--provider", args.provider, "--n-per-class", str(args.n_per_class)])


if __name__ == "__main__":
    raise SystemExit(main())
