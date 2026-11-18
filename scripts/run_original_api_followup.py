#!/usr/bin/env python3
"""Finish original-task capture and the holdout baseline under the existing cumulative budget."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from run_original_api_pilot import (
    IMAGE, MODEL, ROOT, call_model, function, model_trial, sandbox_run, sha, write_json,
)
from trajjudge.cache import canonical_json
from trajjudge.config import ConfigError, load_settings
from trajjudge.llm import LLMClient
from trajjudge.usage import UsageLog, budget_cost, load_pricing, summarize


RUN_ID = "original-api-v2"
MAX_REQUEST_BYTES = 26_000
MAX_TURNS = 6
TRIALS = {
    "event-summary": {"flash-greedy": 0.0, "flash-sampled": 0.35},
    "score-join": {"flash-greedy": 0.0},
}
PUBLIC_ATTEMPT = b"1" + b"0" * 4500


def task_tools(task):
    fixture = "input.jsonl" if task == "event-summary" else "runs.jsonl and reports.jsonl"
    feedback = (
        " It also checks a public example for the visible requirement of an arbitrary-size integer attempt."
        " If the public check fails, you may submit a corrected source."
        if task == "event-summary" else ""
    )
    return [
        function("read_workspace", f"Read the visible starter solution.py and {fixture}.", {}),
        function("submit_solution", f"Replace solution.py with the complete source and run {fixture} to create result.json."
                 f"{feedback} After a successful delivery, give your final reply.",
                 {"source": {"type": "string", "description": "Full Python file contents without Markdown fences."}}),
    ]


def public_probe_case():
    data = b'{"event_id":"public-1","run_id":"public","attempt":' + PUBLIC_ATTEMPT + (
        b',"seq":0,"status":"succeeded"}\n'
    )
    expected = b'{"runs":[{"attempt":' + PUBLIC_ATTEMPT + (
        b',"run_id":"public","status":"succeeded","unique_events":1}],"unique_events":1}\n'
    )
    return data, expected


def public_integer_probe(source):
    data, expected = public_probe_case()
    with TemporaryDirectory(prefix="trajjudge-public-case-") as directory:
        work = Path(directory)
        (work / "solution.py").write_bytes(source)
        (work / "public.jsonl").write_bytes(data)
        try:
            result = sandbox_run(["python3", "-I", "solution.py", "public.jsonl", "public-result.json"],
                                 cwd=work, timeout=8)
        except subprocess.TimeoutExpired:
            return {"case": "4501-digit valid attempt", "status": "timeout"}
        output = work / "public-result.json"
        matched = output.is_file() and not output.is_symlink() and output.read_bytes() == expected
        return {"case": "4501-digit valid attempt", "status": "pass" if result.returncode == 0 and matched else "fail",
                "exit": result.returncode, "stderr": result.stderr[:480].decode("utf-8", errors="replace")}


def prior_accounting(previous, prices):
    plan = json.loads((previous / "budget.json").read_bytes())
    if (plan["run_id"] != "original-api-v1" or plan["mode"] != "live" or plan["cap_usd"] != 0.10
            or plan["plan"]["model"] != MODEL):
        raise ValueError("previous run is not the approved original-api-v1 budget")
    path = previous / "usage.jsonl"
    if not path.is_file() or path.with_suffix(".pending").exists():
        raise ValueError("previous usage ledger is missing or pending")
    records = UsageLog(path).read()
    accounted = budget_cost(records, prices)
    if not records or accounted is None or accounted >= plan["cap_usd"]:
        raise ValueError("previous usage is unknown or the budget is exhausted")
    return path, len(records), accounted, plan["cap_usd"]


def run(previous, output, live):
    settings = load_settings(require_key=live)
    prices = load_pricing(settings.pricing_file)
    prior, prior_rows, prior_cost, cap = prior_accounting(previous, prices)
    if settings.base_url != "https://api.deepseek.com" or settings.agent_model != MODEL:
        raise ValueError("unexpected DeepSeek endpoint or model")
    plan = {"run_id": RUN_ID, "previous_run_id": "original-api-v1", "total_cap_usd": cap,
            "prior_conservative_cost_usd": prior_cost, "remaining_usd": round(cap - prior_cost, 6),
            "previous_usage_sha256": sha(prior.read_bytes()), "model": MODEL, "thinking": False,
            "trials": TRIALS, "max_turns_per_trial": MAX_TURNS, "max_request_bytes": MAX_REQUEST_BYTES,
            "max_attempts_per_call": 1, "sandbox_image": IMAGE}
    if not live:
        print(json.dumps(plan, indent=2))
        return 0
    with TemporaryDirectory(prefix="trajjudge-followup-probe-") as tmp:
        probe = sandbox_run(["python3", "--version"], cwd=Path(tmp), timeout=10)
        if probe.returncode or probe.stdout.strip() != b"Python 3.12.13":
            raise ValueError("pinned Docker interpreter failed its preflight")
    output.mkdir(parents=True)
    write_json(output / "budget.json", plan)
    usage_path = output / "usage.jsonl"
    shutil.copyfile(prior, usage_path)
    client = LLMClient(replace(settings, cache_dir=output / "cache", usage_log=usage_path, budget_usd=cap),
                       max_attempts=1, timeout=60)
    sys.set_int_max_str_digits(0)
    all_trials = {}
    stopped = False
    for task_id, trial_plan in TRIALS.items():
        task = ROOT / task_id
        destination = output / "evidence" / task_id
        destination.mkdir(parents=True)
        tools = task_tools(task_id)
        trials = {}
        all_trials[task_id] = trials
        for name, temperature in trial_plan.items():
            if stopped:
                break

            def generate(messages, turn):
                tag = f"{RUN_ID}/{task_id}/{name}/{turn}"
                return call_model(client, messages, temperature, tag, tag, tools=tools,
                                  max_request_bytes=MAX_REQUEST_BYTES)

            row = model_trial(generate, name, task, destination, "model_run", tools=tools, max_turns=MAX_TURNS,
                              public_check=public_integer_probe if task_id == "event-summary" else None)
            trials[name] = row
            print(f"{task_id}/{name}: {row['capture_status']}, verifier exit {row['verifier_exit']}", flush=True)
            if row["capture_status"] == "api_error" or row["verifier_exit"] == 2:
                stopped = True
        write_json(destination / "matrix.json", {
            "task": task_id, "task_version": 1, "instruction_sha256": sha((task / "instruction.md").read_bytes()),
            "environment": {"python": "3.12.13", "container_image": IMAGE, "network": "none",
                            "tool_schema_sha256": sha(canonical_json(tools).encode()),
                            "public_check": "unbounded-integer-v1" if task_id == "event-summary" else None},
            "matrix": trials,
        })
    records = client.usage_log.read()
    batch = summarize(records[prior_rows:], prices)
    cumulative = budget_cost(records, prices)
    write_json(output / "summary.json", {"run_id": RUN_ID, "cumulative_conservative_cost_usd": cumulative,
               "batch_cost_usd": batch.cost_usd, "new_requests": batch.calls - batch.cached_calls,
               "batch_prompt_tokens": batch.prompt_tokens, "batch_completion_tokens": batch.completion_tokens,
               "prior_usage_rows": prior_rows, "trials": all_trials})
    if cumulative is None or cumulative > cap:
        raise ValueError("cumulative accounting could not be reconciled within the approved cap")
    return int(stopped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="execute the fixed follow-up on the existing budget")
    parser.add_argument("--previous", type=Path, default=Path("outputs/original-api-pilot/original-api-v1"))
    parser.add_argument("--output", type=Path, default=Path("outputs/original-api-pilot/original-api-v2"))
    args = parser.parse_args()
    try:
        raise SystemExit(run(args.previous, args.output, args.run))
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"follow-up failed: {exc}\n")
