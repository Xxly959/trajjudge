#!/usr/bin/env python
"""P3.2: repeated judge runs over P2 trajectories (RQ2). Estimate by default; --run spends money.

Grid subset (all strategies x thinking x graders x repeats) on --grid-traces traces, plus a
Direct-only sweep over every trace. Resumable: finished rows are skipped.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from trajjudge.adapter import adapt_trace  # noqa: E402
from trajjudge.artifacts import artifact_path  # noqa: E402
from trajjudge.config import load_settings  # noqa: E402
from trajjudge.judging import LLM_GRADERS, JudgeConfig, estimate_cost, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402
from trajjudge.usage import load_pricing, summarize  # noqa: E402

OUT = root / "outputs" / "p3" / "stability.jsonl"
STRATEGIES = (("direct", 1), ("average", 3), ("voting", 3))
SEED = 20261106


def load_traces() -> dict[str, list[dict]]:
    """Adapt every complete P2 trace; return trace_id -> messages (unmappable traces are reported, not scored)."""
    found, skipped = {}, []
    for config in ("flash-think-off", "flash-think-on"):
        manifest = root / "outputs" / "claw_eval" / "p2" / config / "manifest.jsonl"
        if not manifest.is_file():
            continue
        for line in manifest.read_text().splitlines():
            row = json.loads(line)
            if row["status"] != "complete":
                continue
            try:
                trace = adapt_trace(artifact_path(row["trace"], root), sidecar_path=artifact_path(row["sidecar"], root))
                if trace.metadata["unmapped_content"] or not trace.metadata["has_trace_end"]:
                    raise ValueError("partial mapping")
                found[trace.trace_id] = trace.messages
            except ValueError as exc:
                skipped.append((row["task_id"], str(exc)))
    if skipped:
        print("skipped traces:", skipped)
    return found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid-traces", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--cap-usd", type=float, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--avg-completion-off", type=int, default=200)
    parser.add_argument("--avg-completion-on", type=int, default=1500)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    traces = load_traces()
    ids = sorted(traces)
    grid_ids = sorted(random.Random(SEED).sample(ids, min(args.grid_traces, len(ids))))
    jobs, est = [], 0.0
    for trace_id in ids:
        for grader in LLM_GRADERS:
            for think in (False, True):
                for strategy, n in (STRATEGIES if trace_id in grid_ids else STRATEGIES[:1]):
                    cfg = JudgeConfig(grader, think, strategy, n)
                    prompt = sum(len(json.dumps(m, ensure_ascii=False)) for m in traces[trace_id]) // 3 + 700
                    for rep in range(args.repeats):
                        jobs.append((trace_id, traces[trace_id], cfg, rep, "original"))
                        est += estimate_cost(n, prompt, args.avg_completion_on if think else args.avg_completion_off)
    calls = sum(j[2].num_evaluations for j in jobs)
    print(json.dumps({"traces": len(ids), "grid_traces": len(grid_ids), "jobs": len(jobs), "completions": calls,
                      "peak_estimate_usd": round(est, 3), "cap_usd": args.cap_usd}))
    if args.run:
        settings = load_settings()
        pricing = load_pricing(settings.pricing_file)
        before = summarize(LLMClient(settings).usage_log.read(), pricing).cost_usd
        client = LLMClient(replace(settings, budget_usd=before + args.cap_usd), max_attempts=4, timeout=180)
        print(run_jobs(jobs, client, OUT, workers=args.workers))
