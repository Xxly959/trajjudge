#!/usr/bin/env python
"""P3.1 probe: do temperature settings take effect with thinking on/off? How long are thinking-on outputs?

Grades one fixed trace repeatedly (accuracy grader) per (thinking, temperature) and reports
score variety, distinct reasons and completion-token spread. Run with --run to spend money.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.adapter import adapt_trace  # noqa: E402
from trajjudge.config import load_settings  # noqa: E402
from trajjudge.judging import JudgeConfig, estimate_cost, latest_rows, load_rows, run_jobs  # noqa: E402
from trajjudge.llm import LLMClient  # noqa: E402

OUT = root / "outputs" / "p3" / "probe_sampling.jsonl"
TEMPS = (None, 0.0, 1.5)
REPEATS = 5

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    fixture = root / "tests" / "fixtures" / "claw_s5"
    trace = adapt_trace(fixture / "email.jsonl", sidecar_path=fixture / "email.sidecar.jsonl")
    jobs = [(trace.trace_id, trace.messages, JudgeConfig("trajectory_accuracy", think, temperature=t), r, "probe")
            for think in (False, True) for t in TEMPS for r in range(REPEATS)]
    print(f"{len(jobs)} calls; peak estimate ${estimate_cost(len(jobs), 4000, 1500):.3f}")
    if args.run:
        client = LLMClient(load_settings(), max_attempts=3, timeout=120)
        print(run_jobs(jobs, client, OUT, workers=6))
    groups: dict[str, list[dict]] = {}
    for row in latest_rows(load_rows(OUT)):
        groups.setdefault(row["config"], []).append(row)
    for name, rows in sorted(groups.items()):
        ok = [r for r in rows if r["status"] == "ok"]
        print(json.dumps({"config": name, "n": len(rows), "errors": len(rows) - len(ok),
                          "scores": sorted(r["score"] for r in ok), "distinct_reasons": len({r["reason"] for r in ok}),
                          "completion_tokens": sorted(r["usage"]["completion_tokens"] for r in ok),
                          "err_sample": next((r["reason"] for r in rows if r["status"] != "ok"), None)}))
