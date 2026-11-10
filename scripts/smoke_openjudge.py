"""Run the S3 weather fixture through native OpenJudge with cached DeepSeek IO."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import sys
from dataclasses import asdict, replace
from typing import Any

from openjudge.graders.agent import TrajectoryAccuracyGrader
from openjudge.graders.schema import GraderScore

from trajjudge.config import PROJECT_ROOT, load_settings
from trajjudge.llm import LLMClient, LLMError
from trajjudge.openjudge_bridge import openjudge_model
from trajjudge.usage import load_pricing, summarize, utc_now


async def evaluate(client: LLMClient, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate once, rejecting error objects and recording observed wire parameters."""
    async with openjudge_model(client, thinking=False, max_tokens=768) as (model, bridge):
        result = await TrajectoryAccuracyGrader(model=model).aevaluate(messages=messages)
        if not isinstance(result, GraderScore) or not math.isfinite(result.score) or not 1 <= result.score <= 3 or not result.reason.strip():
            raise LLMError("OpenJudge did not return a valid trajectory-accuracy score")
        if len(bridge.results) != 1:
            raise LLMError("weather smoke expected one model completion")
        completion = bridge.results[0]
        if completion.returned_reasoning:
            raise LLMError("weather smoke returned reasoning despite disabled thinking")
        commit = subprocess.check_output(["git", "-C", str(PROJECT_ROOT.parent / "OpenJudge"), "rev-parse", "HEAD"], text=True).strip()
        return {
            "trace_id": "openjudge-docs-weather", "grader": result.name,
            "score": result.score, "reason": result.reason, "metadata": result.metadata,
            "judge_model": completion.model, "thinking": completion.thinking,
            "returned_reasoning": completion.returned_reasoning,
            "openjudge_commit": commit, "timestamp": utc_now(), "cached": completion.cached,
            "response_format_policy": "json_object with local validation against the upstream callback schema",
            "wire_observations": bridge.observations,
            "usage": {"prompt_tokens": completion.prompt_tokens, "completion_tokens": completion.completion_tokens,
                      "raw_usage": completion.raw_response.get("usage", {})},
        }


def main(argv: list[str] | None = None) -> int:
    """Print the estimate before any paid request and save a reviewable result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    settings = load_settings(require_key=not args.offline)
    client = LLMClient(settings, offline=args.offline, max_attempts=3, timeout=60)
    models = client.list_models()
    if settings.judge_model not in models:
        raise LLMError("configured judge is not in the discovered model list")
    pricing = load_pricing(settings.pricing_file)
    price = pricing.get(settings.judge_model)
    if price is None:
        raise LLMError("verified pricing is required")
    estimate = {"completion_calls": 1, "input_tokens_estimate": 1200, "output_tokens_cap": 768,
                "cost_usd_estimate": round((1200 * price.input_per_mtok + 768 * price.output_per_mtok) / 1_000_000, 6),
                "reserve_usd": 0.02, "pricing_basis": "peak/cache-miss conservative estimate"}
    print(json.dumps({"estimate": estimate}), flush=True)
    if args.estimate:
        return 0
    before = summarize(client.usage_log.read(), pricing)
    if not args.offline:
        if before.cost_usd is None:
            raise LLMError("unknown historical cost blocks weather smoke")
        client.settings = replace(settings, budget_usd=min(settings.budget_usd, before.cost_usd + 0.02))
    sample = json.loads((PROJECT_ROOT / "samples" / "weather.json").read_text())
    result = asyncio.run(evaluate(client, sample["messages"]))
    result["sample_source"] = sample["metadata"]
    result["estimate"] = estimate
    result["cumulative_usage"] = asdict(summarize(client.usage_log.read(), pricing))
    output = (PROJECT_ROOT / "outputs" / "openjudge" / "weather-score-offline.json") if args.offline else (PROJECT_ROOT / "samples" / "weather-score.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    with (PROJECT_ROOT / "notes" / "log.md").open("a", encoding="utf-8") as stream:
        stream.write("\n\n### S3 天气冒烟（" + result["timestamp"] + "）\n\n")
        stream.write("命令：`python scripts/smoke_openjudge.py " + " ".join(argv or []) + "`\n\n")
        stream.write("```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (LLMError, OSError, ValueError) as exc:
        print(f"OpenJudge smoke stopped ({type(exc).__name__}); inspect safe local usage records.", file=sys.stderr)
        raise SystemExit(1) from None
