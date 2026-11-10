"""Bounded DeepSeek connectivity and thinking/tool-call probe for stage S2."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from typing import Any

from .config import PROJECT_ROOT, load_settings
from .llm import LLMClient, LLMError, LLMResult, assistant_message, tool_result_message
from .usage import load_pricing, summarize, utc_now

TOOLS: list[dict[str, Any]] = [{
    "type": "function",
    "function": {
        "name": "get_probe_code",
        "description": "Return the local smoke-test verification code. No network access.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}]
TOOL_CODE = "S2_TOOL_OK_731"
OUTPUT_CAPS = (64, 64, 1024, 1536, 1536)


def run_smoke(client: LLMClient, model: str) -> list[dict[str, Any]]:
    """Run five bounded completions, preserving reasoning verbatim across tools.

    All tools are deterministic local fixtures. Failures are not labelled passes;
    their completions and usage remain in the shared cache and usage log.
    """
    rows: list[dict[str, Any]] = []
    def record(name: str, result: LLMResult) -> None:
        rows.append({
            "probe": name, "model": result.model, "thinking": result.thinking,
            "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
            "returned_reasoning": result.returned_reasoning, "cached": result.cached,
            "tool_calls": len(result.tool_calls), "answer": result.text,
        })

    plain = client.complete(
        [{"role": "user", "content": "Reply with exactly S2_READY."}],
        model=model, thinking=False, max_tokens=OUTPUT_CAPS[0], tag="s2/plain",
    )
    record("plain", plain)
    if plain.text.strip() != "S2_READY" or plain.tool_calls:
        raise LLMError("plain probe did not return the expected answer")

    for name, thinking, cap in (("thinking_off", False, OUTPUT_CAPS[1]), ("thinking_on", True, OUTPUT_CAPS[2])):
        result = client.complete(
            [{"role": "user", "content": "What is 2 + 3? Reply with only the integer."}],
            model=model, thinking=thinking, max_tokens=cap,
            reasoning_effort="low" if thinking else None, tag=f"s2/{name}",
        )
        record(name, result)
        if result.text.strip() != "5" or result.tool_calls:
            raise LLMError(f"{name} probe did not return the expected answer")
        if result.returned_reasoning != thinking:
            raise LLMError(f"{name} reasoning_content presence did not match the requested mode")

    messages: list[dict[str, Any]] = [{
        "role": "user",
        "content": "Call get_probe_code exactly once to retrieve the verification code. Do not guess. After the tool result, reply with only its code.",
    }]
    first = client.complete(
        messages, model=model, thinking=True, tools=TOOLS, reasoning_effort="low",
        max_tokens=OUTPUT_CAPS[3], tag="s2/tool_request",
    )
    record("tool_request", first)
    if not first.returned_reasoning:
        raise LLMError("thinking tool request did not return reasoning_content")
    if len(first.tool_calls) != 1 or first.tool_calls[0].name != "get_probe_code":
        raise LLMError("tool probe expected exactly one get_probe_code call")
    try:
        arguments = json.loads(first.tool_calls[0].arguments)
    except json.JSONDecodeError:
        raise LLMError("tool probe returned invalid JSON arguments") from None
    if arguments != {}:
        raise LLMError("tool probe expected empty arguments")
    previous = assistant_message(first)
    if previous.get("reasoning_content") != first.reasoning_content:
        raise LLMError("reasoning_content was altered before replay")
    messages.extend([previous, tool_result_message(first.tool_calls[0], json.dumps({"code": TOOL_CODE}))])
    final = client.complete(
        messages, model=model, thinking=True, tools=TOOLS, tool_choice="none",
        reasoning_effort="low", max_tokens=OUTPUT_CAPS[4], tag="s2/tool_followup",
    )
    record("tool_followup", final)
    if final.text.strip() != TOOL_CODE or final.tool_calls:
        raise LLMError("tool result was not reproduced correctly in the final answer")
    rows[-1]["reasoning_replayed_verbatim"] = True
    return rows


def estimate(client: LLMClient, model: str) -> dict[str, Any]:
    """Report a conservative S2 estimate before any paid batch starts."""
    prices = load_pricing(client.settings.pricing_file)
    if model not in prices:
        raise LLMError("verified model pricing is required for a smoke estimate")
    price = prices[model]
    # Includes a generous allowance for the first tool turn's replayed reasoning.
    input_tokens = 5000
    output_tokens = sum(OUTPUT_CAPS)
    cost = (input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok) / 1_000_000
    return {
        "model": model, "completion_calls": 5, "input_tokens_estimate": input_tokens,
        "output_tokens_cap": output_tokens, "cost_usd_estimate": round(cost, 6),
        "attempt_limit": client.max_attempts, "batch_reserve_usd": 0.05,
        "pricing_basis": "peak input cache-miss and peak output; conservative estimate, not invoice",
    }


def main(argv: list[str] | None = None) -> int:
    """List models or run the smoke batch, writing safe summaries and notes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-models", action="store_true", help="List models without paid completions")
    parser.add_argument("--estimate", action="store_true", help="Print the batch estimate without paid completions")
    parser.add_argument("--offline", action="store_true", help="Require every response to be cached")
    parser.add_argument("--model", help="Model ID, validated against the discovered model list")
    args = parser.parse_args(argv)
    settings = load_settings(require_models=False, require_key=not args.offline)
    client = LLMClient(settings, max_attempts=3, timeout=60, offline=args.offline)
    models = client.list_models()
    print(json.dumps({"models": models, "cached": client.last_models_cached}), flush=True)
    if args.list_models:
        return 0
    model = args.model or settings.judge_model
    if model not in models:
        raise LLMError("select a model ID returned by --list-models")
    batch_estimate = estimate(client, model)
    print(json.dumps({"estimate": batch_estimate}), flush=True)
    if args.estimate:
        return 0
    # Respect both the stage budget and the smaller advertised probe reservation.
    before = summarize(client.usage_log.read(), load_pricing(settings.pricing_file))
    if not args.offline:
        if before.cost_usd is None:
            raise LLMError("unknown historical cost blocks the smoke batch")
        client.settings = replace(settings, budget_usd=min(settings.budget_usd, before.cost_usd + 0.05))
    rows = run_smoke(client, model)
    summary = summarize(client.usage_log.read(), load_pricing(settings.pricing_file))
    payload = {"timestamp": utc_now(), "models": models, "estimate": batch_estimate,
               "offline": args.offline, "results": rows, "cumulative_usage": asdict(summary)}
    filename = "s2-offline.json" if args.offline else "s2.json"
    output = PROJECT_ROOT / "outputs" / "smoke" / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False), flush=True)
    print(json.dumps({"cumulative_usage": asdict(summary)}), flush=True)
    note = PROJECT_ROOT / "notes" / "log.md"
    with note.open("a", encoding="utf-8") as stream:
        stream.write("\n\n### S2 探针结果（" + payload["timestamp"] + "）\n\n")
        stream.write("命令：`" + " ".join(["python scripts/smoke_llm.py", *(argv or [])]) + "`\n\n")
        stream.write("模型列表：`" + ", ".join(models) + "`；离线回放：" + str(args.offline) + "。\n\n")
        stream.write("```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n")
    return 0
