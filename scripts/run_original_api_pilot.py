#!/usr/bin/env python3
"""Capture bounded DeepSeek API trials for the original event-summary training task."""

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
from types import SimpleNamespace
from uuid import uuid4

from build_cross_source import json_document
from build_training_candidates import validate_conversation
from run_original_task import DOCKERFILE, ROOT, input_files, sha, write_json
from trajjudge.cache import canonical_json
from trajjudge.config import ConfigError, load_settings
from trajjudge.llm import LLMClient, LLMError
from trajjudge.usage import load_pricing, summarize


TASK = "event-summary"
IMAGE = DOCKERFILE.splitlines()[0].removeprefix("FROM ")
MODEL = "deepseek-flash"
MAX_TURNS = 6
MAX_TOKENS = 2048
MAX_REQUEST_BYTES = 14_000
TRIALS = {"flash-greedy": 0.0, "flash-sampled": 0.35}


class RequestSizeError(LLMError):
    """A local size guard refused a request before it reached DeepSeek."""


def function(name, description, properties):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": list(properties), "additionalProperties": False,
    }}}


TOOLS = [
    function("read_workspace", "Read the task's visible starter solution.py and input.jsonl.", {}),
    function("submit_solution", "Replace solution.py with the complete Python source, then run the visible fixture "
             "to create result.json. Use this to deliver both required artifacts.",
             {"source": {"type": "string", "description": "Full Python file contents, without Markdown fences."}}),
]


def parse_tool(call):
    name, args = call.name, json_document(call.arguments)
    if not isinstance(call.call_id, str) or not call.call_id.strip():
        raise ValueError("missing tool call ID")
    if name == "read_workspace" and args == {}:
        return name, args
    if (name == "submit_solution" and isinstance(args, dict) and set(args) == {"source"}
            and isinstance(args["source"], str) and 0 < len(args["source"].encode("utf-8")) <= 24_576):
        return name, args
    raise ValueError("unknown tool or invalid tool arguments")


def wire_messages(messages):
    result = []
    for message in messages:
        row = {key: value for key, value in message.items() if key != "name"}
        if "tool_calls" in row:
            row.setdefault("content", "")
            row["tool_calls"] = [
                {**call, "function": {**call["function"], "arguments": canonical_json(call["function"]["arguments"])}}
                for call in row["tool_calls"]
            ]
        result.append(row)
    return result


def docker_command(name, cwd, args):
    return [
        "docker", "run", "--name", name, "--rm", "--pull", "never", "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--pids-limit", "32", "--memory", "256m", "--cpus", "1", "--ulimit", "fsize=262144:262144",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=16m", "--log-driver", "none",
        "--mount", f"type=bind,source={cwd},target=/work", "--workdir", "/work",
        IMAGE, "python3", *args,
    ]


def sandbox_run(command, *, cwd, timeout, **unused):
    name = f"trajjudge-pilot-{uuid4().hex}"
    docker = docker_command(name, Path(cwd).resolve(), command[1:])
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        try:
            result = subprocess.run(docker, stdout=stdout, stderr=stderr, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=8)
            raise subprocess.TimeoutExpired(command, timeout) from None
        stdout.seek(0)
        stderr.seek(0)
        out, err = stdout.read(32768), stderr.read(32768)
    if result.returncode == 125:
        raise OSError(f"Docker could not start candidate: {err.decode('utf-8', errors='replace')[:1000]}")
    return subprocess.CompletedProcess(command, result.returncode, out, err)


def tool_return(name, args, starter, trial, turn, submission_args=("input.jsonl",), public_check=None):
    if name == "read_workspace":
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(starter.iterdir())}
    source = args["source"].encode("utf-8")
    (trial / f"submission-{turn}.py").write_bytes(source)
    final = trial / "last-delivery"
    final.mkdir(exist_ok=True)
    (final / "solution.py").write_bytes(source)
    saved = final / "result.json"
    saved.unlink(missing_ok=True)
    with TemporaryDirectory(prefix="trajjudge-delivery-") as scratch:
        workspace = Path(scratch) / "workspace"
        shutil.copytree(starter, workspace)
        (workspace / "solution.py").write_bytes(source)
        try:
            result = sandbox_run(["python3", "-I", "solution.py", *submission_args, "result.json"], cwd=workspace, timeout=8)
        except subprocess.TimeoutExpired:
            outcome = {"exit": None, "status": "candidate_timeout", "candidate_sha256": sha(source)}
            write_json(trial / "last-delivery.json", outcome)
            return outcome
        target = workspace / "result.json"
        if target.is_file() and not target.is_symlink() and target.stat().st_size <= 262_144:
            shutil.copyfile(target, saved)
        (trial / f"delivery-{turn}-stdout.txt").write_bytes(result.stdout)
        (trial / f"delivery-{turn}-stderr.txt").write_bytes(result.stderr)
        outcome = {"exit": result.returncode, "candidate_sha256": sha(source),
                   "artifact_sha256": sha(saved.read_bytes()) if saved.is_file() else None}
        outcome["result"] = saved.read_bytes()[:4096].decode("utf-8", errors="replace") if saved.is_file() else None
        outcome["stderr"] = result.stderr[:2000].decode("utf-8", errors="replace")
        if public_check is not None and result.returncode == 0 and saved.is_file():
            outcome["public_check"] = public_check(source)
        write_json(trial / "last-delivery.json", outcome)
        return outcome


def verify_candidate(trial, starter, cases):
    verifier = runpy.run_path(str(ROOT / "verify.py"))
    verifier["verify"].__globals__["subprocess"] = SimpleNamespace(run=sandbox_run, TimeoutExpired=subprocess.TimeoutExpired)
    result_dir = trial / "verification"
    result_dir.mkdir()
    with TemporaryDirectory(prefix="trajjudge-final-") as scratch:
        workspace = Path(scratch) / "workspace"
        shutil.copytree(starter, workspace)
        last = trial / "last-delivery"
        if last.is_dir():
            for p in last.iterdir():
                shutil.copyfile(p, workspace / p.name)
        shutil.copyfile(workspace / "solution.py", trial / "submitted-solution.py")
        report = {"verifier_version": verifier["verifier_version"](cases), "checks": []}
        try:
            report["checks"] = verifier["verify"](workspace, cases, result_dir)
            report["exit"] = int(any(check["status"] != "ok" for check in report["checks"]))
        except OSError as exc:
            report["infrastructure_error"] = str(exc)
            report["exit"] = 2
    (result_dir / "checks.json").write_bytes(verifier["canonical"](report))
    return report


def model_trial(generate, name, task, destination, origin, *, tools=TOOLS, max_turns=MAX_TURNS, public_check=None):
    trial = destination / name
    trial.mkdir()
    starter = task / "environment/workspace"
    submission_args = runpy.run_path(str(task / "cases.py"))["SUBMISSION_ARGS"]
    instruction = (task / "instruction.md").read_text(encoding="utf-8")
    messages = [{"role": "user", "content": instruction}]
    raw, status, call_ids, operation = [], "turn_limit", set(), 0
    for turn in range(1, max_turns + 1):
        try:
            result = generate(messages, turn)
        except RequestSizeError as exc:
            status = "local_request_size_limit"
            write_json(trial / "response-error.json", {"detail": str(exc)})
            break
        except LLMError as exc:
            status = "api_error"
            write_json(trial / "response-error.json", {"detail": str(exc)})
            break
        finish = result.raw_response["choices"][0].get("finish_reason")
        raw.append({"turn": turn, "finish_reason": finish, "result": result.to_dict()})
        write_json(trial / "raw-generations.json", raw)
        print(f"{name} turn {turn}: {result.completion_tokens} output tokens, finish={finish}", flush=True)
        if finish not in {"stop", "tool_calls"}:
            status = f"generation_{finish}"
            break
        try:
            calls = [(call.call_id, *parse_tool(call)) for call in result.tool_calls]
            ids = {call_id for call_id, _, _ in calls}
            if len(ids) != len(calls) or ids & call_ids:
                raise ValueError("duplicate tool call ID")
            if bool(calls) != (finish == "tool_calls"):
                raise ValueError("tool calls disagree with the provider finish reason")
            if not calls and not result.text.strip():
                raise ValueError("empty final reply")
        except (ValueError, TypeError) as exc:
            status = "invalid_tool_or_response"
            write_json(trial / "response-error.json", {"detail": str(exc)})
            break
        if not calls:
            messages.append({"role": "assistant", "content": result.text})
            (trial / "final-reply.txt").write_text(result.text + "\n", encoding="utf-8")
            status = "final_reply"
            break
        assistant = {"role": "assistant", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": fn, "arguments": args}}
            for call_id, fn, args in calls
        ]}
        if result.text:
            assistant["content"] = result.text
        messages.append(assistant)
        call_ids.update(ids)
        for call_id, fn, args in calls:
            operation += 1
            observation = tool_return(fn, args, starter, trial, operation, submission_args, public_check)
            messages.append({"role": "tool", "tool_call_id": call_id, "name": fn,
                             "content": json.dumps(observation, ensure_ascii=False, sort_keys=True)})
        write_json(trial / "messages-so-far.json", messages)
    report = verify_candidate(trial, starter, task / "cases.py")
    artifact = trial / "verification/submitted-result.json"
    complete = False
    if status == "final_reply":
        try:
            validate_conversation(messages, tools)
            complete = True
        except ValueError:
            status = "final_reply_without_complete_tool_interaction"
    source = sha((trial / "submitted-solution.py").read_bytes())
    write_json(trial / "trajectory.json", {
        "schema_version": 1, "complete": complete, "source_id": f"original:{task.name}:v1:{name}",
        "origin": origin, "candidate_sha256": source, "verifier_version": report["verifier_version"],
        "checks_sha256": sha((trial / "verification/checks.json").read_bytes()),
        "artifact_sha256": sha(artifact.read_bytes()) if artifact.is_file() else None,
        "messages": messages, "tools": tools, "capture_status": status,
    })
    failed = {item["id"]: item["status"] for item in report["checks"] if item["status"] != "ok"}
    return {"source": origin, "candidate_sha256": source, "starting_files": input_files(starter),
            "verifier_exit": report["exit"], "verifier_version": report["verifier_version"],
            "checks": len(report["checks"]), "failed_checks": failed, "capture_status": status,
            "completion_tokens": sum(item["result"]["completion_tokens"] for item in raw)}


def estimate(settings):
    price = load_pricing(settings.pricing_file)[MODEL]
    request_count = len(TRIALS) * MAX_TURNS
    per_call = ((MAX_REQUEST_BYTES + 4096) * price.input_per_mtok + MAX_TOKENS * price.output_per_mtok) / 1_000_000
    return {"model": MODEL, "task": TASK, "thinking": False, "trials": TRIALS, "max_calls": request_count,
            "max_turns": MAX_TURNS, "max_output_tokens_per_call": MAX_TOKENS, "max_request_bytes": MAX_REQUEST_BYTES,
            "max_attempts_per_call": 1, "estimated_peak_upper_bound_usd": round(per_call * request_count, 8)}


def call_model(client, messages, temperature, repeat_id, tag, *, tools=TOOLS, max_request_bytes=MAX_REQUEST_BYTES):
    wire = wire_messages(messages)
    request = {"messages": wire, "model": MODEL, "temperature": temperature, "tools": tools,
               "max_tokens": MAX_TOKENS, "extra_body": {"thinking": {"type": "disabled"}}}
    size = len(canonical_json(request).encode())
    if size > max_request_bytes:
        raise RequestSizeError(f"local request size {size} exceeds {max_request_bytes} bytes")
    return client.complete(wire, model=MODEL, thinking=False, tools=tools, max_tokens=MAX_TOKENS,
                           temperature=temperature, repeat_id=repeat_id, tag=tag)


def rehearsal_transport(task):
    source = (task / "solution/reference.py").read_text(encoding="utf-8")

    def transport(request):
        count = sum(row["role"] == "tool" for row in request["messages"])
        if count < 2:
            name, args = ("read_workspace", {}) if count == 0 else ("submit_solution", {"source": source})
            message = {"content": None, "tool_calls": [{"id": f"mock-{count}", "type": "function",
                       "function": {"name": name, "arguments": json.dumps(args)}}]}
            finish = "tool_calls"
        else:
            message, finish = {"content": "合成演练已生成 result.json。"}, "stop"
        return {"choices": [{"message": message, "finish_reason": finish}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 12}, "model": MODEL}

    return transport


def run(settings, output, eval_evidence, run_id, cap, rehearsal):
    if settings.base_url != "https://api.deepseek.com" or settings.agent_model != MODEL:
        raise ValueError("pilot expects the project's official DeepSeek endpoint and flash agent model")
    if not (eval_evidence / "matrix.json").is_file():
        raise ValueError("expected existing P2 score-join evidence")
    with TemporaryDirectory(prefix="trajjudge-sandbox-probe-") as tmp:
        probe = sandbox_run(["python3", "--version"], cwd=Path(tmp), timeout=10)
        if probe.returncode or probe.stdout.strip() != b"Python 3.12.13":
            raise ValueError("pinned Docker interpreter failed its preflight")
    output.mkdir(parents=True)
    plan = estimate(settings)
    write_json(output / "budget.json", {"run_id": run_id, "cap_usd": None if rehearsal else cap, "plan": plan,
                                       "mode": "mocked_rehearsal" if rehearsal else "live", "sandbox_image": IMAGE})
    settings = replace(settings, cache_dir=output / "cache", usage_log=output / "usage.jsonl",
                       budget_usd=1.0 if rehearsal else cap)
    sys.set_int_max_str_digits(0)
    evidence = output / "evidence" / TASK
    evidence.mkdir(parents=True)
    task = ROOT / TASK
    client = LLMClient(settings, transport=rehearsal_transport(task) if rehearsal else None, max_attempts=1, timeout=60)
    origin = "constructed_fixture" if rehearsal else "model_run"
    trials = {}
    for name, temperature in TRIALS.items():
        def generate(messages, turn):
            tag = f"{run_id}/{name}/{turn}"
            return call_model(client, messages, temperature, tag, tag)

        trials[name] = model_trial(generate, name, task, evidence, origin)
        print(f"{name}: {trials[name]['capture_status']}, verifier exit {trials[name]['verifier_exit']}", flush=True)
        if trials[name]["capture_status"] in {"api_error", "local_request_size_limit"} or trials[name]["verifier_exit"] == 2:
            break
    write_json(evidence / "matrix.json", {
        "task": TASK, "task_version": 1, "instruction_sha256": sha((task / "instruction.md").read_bytes()),
        "environment": {"python": "3.12.13", "container_image": IMAGE, "network": "none",
                        "tool_schema_sha256": sha(json.dumps(TOOLS, sort_keys=True).encode())}, "matrix": trials,
    })
    shutil.copytree(eval_evidence, output / "evidence/score-join")
    summary = summarize(client.usage_log.read(), load_pricing(settings.pricing_file))
    write_json(output / "summary.json", {"mode": "mocked_rehearsal" if rehearsal else "live",
                                       "requests": summary.calls - summary.cached_calls,
                                       "cache_hits": summary.cached_calls,
                                       "cost_usd": None if rehearsal else summary.cost_usd,
                                       "trials": trials})
    return int(len(trials) != len(TRIALS) or any(
        row["verifier_exit"] == 2 or row["capture_status"] in {"api_error", "local_request_size_limit"} for row in trials.values()
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--rehearse", action="store_true", help="run with synthetic API replies and real Docker")
    modes.add_argument("--run", action="store_true", help="start the owner-approved paid run")
    parser.add_argument("--eval-evidence", type=Path, default=ROOT.parents[1] / "outputs/original-tasks/p2/v1-run-a/score-join")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--cap-usd", type=float)
    args = parser.parse_args()
    if args.run and (args.cap_usd is None or not math.isfinite(args.cap_usd) or args.cap_usd <= 0):
        parser.error("live mode requires an owner-approved positive --cap-usd")
    if (args.run or args.rehearse) and (args.output is None or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.run_id or "")):
        parser.error("set --output and a new --run-id for this run")
    try:
        settings = load_settings(require_key=args.run)
        if not (args.run or args.rehearse):
            print(json.dumps(estimate(settings), indent=2))
        else:
            raise SystemExit(run(settings, args.output, args.eval_evidence, args.run_id, args.cap_usd, args.rehearse))
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"pilot failed: {exc}\n")
