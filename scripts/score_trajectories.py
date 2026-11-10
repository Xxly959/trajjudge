"""Score the completed S5 pilot; default to an estimate, or replay offline."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any

from trajjudge.adapter import AdaptedTrace, adapt_trace
from trajjudge.artifacts import artifact_path
from trajjudge.config import PROJECT_ROOT, ConfigError, load_settings
from trajjudge.llm import LLMClient, LLMError
from trajjudge.runner import GRADERS, run_graders
from trajjudge.usage import load_pricing, summarize, utc_now


def load_pilot_traces(path: Path) -> list[AdaptedTrace]:
    """Require completed, identified pilot artifacts and their real system text."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks", [])
    if manifest.get("status") != "complete" or not 1 <= len(tasks) <= 3:
        raise ValueError("a completed pilot with one to three tasks is required")
    traces: list[AdaptedTrace] = []
    for task in tasks:
        trace = adapt_trace(artifact_path(task["trial"]["trace"], PROJECT_ROOT),
                            sidecar_path=artifact_path(task["sidecar"], PROJECT_ROOT))
        official = trace.metadata.get("official_result")
        if trace.task_id != task["task_id"] or not trace.metadata["has_trace_end"]:
            raise ValueError("pilot task identity or completion does not match its trace")
        if trace.metadata["system_source"]["kind"] == "missing" or trace.metadata["unmapped_content"]:
            raise ValueError("pilot requires complete messages including the actual system prompt")
        if not official or official.get("task_score") != task["trial"]["task_score"]:
            raise ValueError("pilot and native grading_result scores disagree")
        traces.append(trace)
    if len({trace.trace_id for trace in traces}) != len(traces):
        raise ValueError("duplicate pilot trace IDs")
    return traces


def main(argv: list[str] | None = None) -> int:
    """Bound the paid batch and retain both successful and failed verdicts."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="run the reviewed S6 batch")
    mode.add_argument("--offline", action="store_true", help="require cached responses; never use the network")
    mode.add_argument("--estimate", action="store_true", help="print the estimate only (default)")
    args = parser.parse_args(argv)
    settings = load_settings(require_key=args.run)
    traces = load_pilot_traces(PROJECT_ROOT / "outputs" / "claw_eval" / "s5" / "pilot.json")
    client = LLMClient(settings, offline=not args.run, max_attempts=3, timeout=60)
    pricing = load_pricing(settings.pricing_file)
    price = pricing.get(settings.judge_model)
    if price is None:
        raise LLMError("verified pricing is required")
    # Planning estimates include native prompts and full trace text. The shared
    # client separately reserves each actual request, including retry attempts.
    inputs, outputs = 15_000 * len(traces), 4096 * len(traces)
    cost = (Decimal(inputs) * Decimal(str(price.input_per_mtok)) +
            Decimal(outputs) * Decimal(str(price.output_per_mtok))) / Decimal(1_000_000)
    estimate = {"traces": len(traces), "completion_calls": 2 * len(traces),
                "rule_evaluations": 2 * len(traces), "input_tokens_estimate": inputs,
                "output_tokens_cap": outputs, "cost_usd_estimate": float(cost.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)),
                "batch_reserve_usd": 0.15, "stage_budget_usd": settings.budget_usd,
                "pricing_basis": "peak/cache-miss conservative estimate; retries reserved separately"}
    print(json.dumps({"estimate": estimate}), flush=True)
    if not args.run and not args.offline:
        return 0
    target = PROJECT_ROOT / "outputs" / "grades"
    output = target / ("s6-offline.jsonl" if args.offline else "s6.jsonl")
    if args.run and output.exists():
        raise LLMError("S6 output already exists; use --offline to replay without new calls")
    before_records = client.usage_log.read()
    before = summarize(before_records, pricing)
    if args.run:
        if before.cost_usd is None:
            raise LLMError("unknown historical cost blocks paid scoring")
        client.settings = replace(settings, budget_usd=min(settings.budget_usd, before.cost_usd + 0.15))
    rows = run_graders(traces, client, output=output)
    records = client.usage_log.read()
    summary: dict[str, Any] = {
        "timestamp": utc_now(), "offline": args.offline, "estimate": estimate,
        "status": "complete" if len(rows) == len(traces) * len(GRADERS) and all(row.status == "ok" for row in rows) else "incomplete",
        "output": str(output), "judge_model": settings.judge_model, "thinking": settings.judge_thinking,
        "batch_usage": asdict(summarize(records[len(before_records):], pricing)),
        "cumulative_usage": asdict(summarize(records, pricing)),
        "scores": [{"trace_id": row.trace_id, "task_id": row.metadata["task_id"], "grader": row.grader,
                    "status": row.status, "score": row.score, "usage": row.usage} for row in rows],
    }
    output.with_suffix(".summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (ConfigError, LLMError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"S6 scoring stopped ({type(exc).__name__}); inspect local artifacts and safe usage records.", file=sys.stderr)
        raise SystemExit(1) from None
