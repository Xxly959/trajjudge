#!/usr/bin/env python
"""Plan, run or replay frozen P2/P3/P4 jobs; no paid request without --run and a cap."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.adapter import adapt_trace
from trajjudge.analysis import join_labels
from trajjudge.annotation import read_labels
from trajjudge.artifacts import atomic_text
from trajjudge.config import load_settings
from trajjudge.judging import JudgeConfig, LLM_GRADERS, RULE_GRADERS, openjudge_commit, rule_row, run_jobs
from trajjudge.llm import LLMClient
from trajjudge.perturb import TEMPLATES, LOCATIONS, inject
from trajjudge.usage import load_pricing, summarize, budget_cost, load_reservations


def frozen_traces() -> dict[str, list[dict]]:
    """Load selected local evidence only after verifying frozen content hashes."""
    traces = {}
    for item in json.loads((root / "outputs/p2/annotation_set.json").read_text()):
        for key in ("trace", "sidecar"):
            if hashlib.sha256(Path(item[key]).read_bytes()).hexdigest() != item[f"{key}_sha256"]:
                raise ValueError("frozen evidence changed")
        trace = adapt_trace(Path(item["trace"]), sidecar_path=Path(item["sidecar"]))
        if trace.metadata["unmapped_content"] or not trace.metadata["has_trace_end"]:
            raise ValueError("incomplete adapted trace")
        traces[trace.trace_id] = trace.messages
    return traces


def human_fail_ids(*, expected_unlabeled: int = 0) -> set[str]:
    """Read actual owner labels; never substitute framework labels for human labels."""
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text())
    key = json.loads((root / "outputs/annotation/key.json").read_text())
    joined = join_labels(meta["chosen"], key, read_labels(root / "annotation/labels.csv"), [])
    unlabeled = joined["selected"] - joined["labeled"]
    if unlabeled != expected_unlabeled:
        raise ValueError(f"expected {expected_unlabeled} unlabeled traces for P4, found {unlabeled}")
    return {r["trace_id"] for r in joined["rows"] if not r["human"]}


def variants(messages: list[dict]):
    """Yield original and the eight benign, defensive-evaluation-only variants."""
    yield "original", messages
    for template in TEMPLATES:
        for location in LOCATIONS:
            try:
                changed, _ = inject(messages, template.template_id, location)
            except ValueError:
                continue
            yield f"{template.template_id}/{location}", changed


def main() -> int:
    """Default to a cost plan; controls are free, offline replay refuses cache misses."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("p2", "p3", "p4", "probe", "controls"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--offline", action="store_true")
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--model", choices=("deepseek-flash", "deepseek-v4-pro"), default="deepseek-flash")
    parser.add_argument("--thinking", choices=("on", "off", "both"), default="on")
    parser.add_argument("--grid-traces", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3, help="transport attempts per completion; does not change sampling parameters")
    parser.add_argument("--run-id")
    parser.add_argument("--limit", type=int, default=0, help="fixed trace-id ordered pilot subset; 0 means all")
    parser.add_argument("--expected-unlabeled", type=int, default=0,
                        help="P4 only: require this exact number of unlabeled traces and exclude them")
    args = parser.parse_args()
    if args.expected_unlabeled < 0 or (args.expected_unlabeled and args.phase != "p4"):
        parser.error("--expected-unlabeled requires a nonnegative count and P4")
    if args.repeats < 3 or args.grid_traces < 0 or args.workers < 1 or args.max_attempts < 1:
        parser.error("need repeats>=3, grid-traces>=0 and workers>=1")
    if args.run and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("paid execution needs an explicitly approved positive --cap-usd")
    run_id = args.run_id or f"{args.phase}-{args.model}"
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        parser.error("run-id must contain only letters, digits, hyphens and underscores")
    traces = frozen_traces()
    run_dir = root / "runs" / run_id
    output = root / "outputs" / args.phase / f"{run_id}.jsonl"
    if args.phase == "controls":
        from trajjudge.cache import DiskCache, make_key
        cache = DiskCache(run_dir / "rows")
        rows, descriptors = [], []
        for tid, messages in sorted(traces.items()):
            for variant, changed in variants(messages):
                for grader in RULE_GRADERS:
                    descriptor = {"trace_id": tid, "variant": variant, "grader": grader,
                                  "input_hash": make_key({"messages": changed}), "commit": openjudge_commit()}
                    identity = make_key(descriptor)
                    row = cache.get(identity)
                    if row is None:
                        row = rule_row(tid, changed, grader, descriptor["commit"], variant)
                        cache.put(identity, row)
                    rows.append(row)
                    descriptors.append(identity)
                    atomic_text(run_dir / "manifest.json", json.dumps({"kind": "free exploratory rule controls",
                        "selected_traces": len(traces), "completed": descriptors, "status": "running"}))
        atomic_text(output, "".join(json.dumps(r) + "\n" for r in rows))
        atomic_text(run_dir / "manifest.json", json.dumps({"kind": "free exploratory rule controls",
            "selected_traces": len(traces), "total_jobs": len(rows), "completed": descriptors, "status": "complete"}))
        print(json.dumps({"rule_evaluations": len(rows), "new_paid_cost_usd": 0, "output": str(output)}))
        return 0
    if args.phase == "p4":
        allowed = human_fail_ids(expected_unlabeled=args.expected_unlabeled)
        traces = {k: v for k, v in traces.items() if k in allowed}
        if not traces:
            raise ValueError("no human-fail traces; no formal injection experiment can be run")
    if args.limit:
        if args.limit < 0:
            parser.error("limit must be nonnegative")
        traces = dict(sorted(traces.items())[:args.limit])
    thinking = [False, True] if args.thinking == "both" else [args.thinking == "on"]
    if args.phase == "p2":
        thinking = [False]  # D24 frozen main configuration
    jobs = []
    for index, (tid, messages) in enumerate(sorted(traces.items())):
        for variant, changed in (variants(messages) if args.phase == "p4" else [("original", messages)]):
            for grader in LLM_GRADERS:
                for think in thinking:
                    strategies = [("direct", 1)]
                    if args.phase == "p3" and index < args.grid_traces:
                        strategies += [("average", 3), ("voting", 3)]
                    for strategy, n in strategies:
                        for defended in ([False, True] if args.phase == "p4" else [False]):
                            config = JudgeConfig(grader, think, strategy, n, defended=defended)
                            for repeat in range(1 if args.phase == "p2" else args.repeats):
                                jobs.append((tid, changed, config, repeat, variant))
    if args.phase == "probe":
        tid, messages = sorted(traces.items())[0]
        jobs = [(tid, messages, JudgeConfig("trajectory_accuracy", think, temperature=temp), repeat, "sampling_probe")
                for think in (False, True) for temp in (None, 0., 1.5) for repeat in range(args.repeats)]
    settings = replace(load_settings(require_key=args.run), judge_model=args.model, pricing_file=root / "configs/pricing_p3.yaml")
    price = load_pricing(settings.pricing_file).get(args.model)
    if price is None:
        raise ValueError("model is unpriced; supply verified pricing before planning or executing this model")
    estimate = sum(j[2].num_evaluations * ((len(json.dumps(j[1], ensure_ascii=False)) // 3 + 1500) * price.input_per_mtok
                   + j[2].effective_max_tokens * price.output_per_mtok) / 1_000_000 for j in jobs)
    print(json.dumps({"phase": args.phase, "traces": len(traces), "jobs": len(jobs),
        "completions": sum(j[2].num_evaluations for j in jobs), "peak_cap_based_estimate_usd": round(estimate, 6),
        "note": "character-based input estimate; excludes retry reserve; not an invoice or budget approval"}))
    if not args.run and not args.offline:
        return 0
    if args.run:
        budget_path = run_dir / "budget.json"
        if budget_path.exists():
            budget = json.loads(budget_path.read_text())
            if budget["stage_cap_usd"] != args.cap_usd:
                raise ValueError("resume must preserve original stage cap")
        else:
            before = budget_cost(LLMClient(settings).usage_log.read(), load_pricing(settings.pricing_file), load_reservations(settings.usage_log))
            if before is None:
                raise ValueError("historical spend unknown; reconcile first")
            budget = {"stage_cap_usd": args.cap_usd, "spent_before_usd": before, "ceiling_usd": before + args.cap_usd,
                      "basis": "known conservative costs plus unknown-attempt reservations; not actual billing"}
            atomic_text(budget_path, json.dumps(budget, indent=2))
        settings = replace(settings, budget_usd=budget["ceiling_usd"])
    client = LLMClient(settings, offline=args.offline, max_attempts=args.max_attempts)
    counts = run_jobs(jobs, client, output, workers=args.workers, run_dir=run_dir, phase=args.phase)
    print(json.dumps(counts))
    return int(bool(counts["error"] or counts["stopped_early"]))


if __name__ == "__main__":
    raise SystemExit(main())
