"""Preflight and run exactly the two user-approved S5 tasks, once each."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import platform
import socket
import subprocess
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from .claw_bridge import INPUT_ESTIMATE_CAP, S5Stop, TASKS, bounded_worker
from .config import PROJECT_ROOT, Settings, load_settings
from .llm import LLMClient
from .usage import load_pricing, summarize, utc_now

UPSTREAM = PROJECT_ROOT.parent / "claw-eval"
EXPECTED_COMMIT = "5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7"
OUTPUT = PROJECT_ROOT / "outputs" / "claw_eval" / "s5"
CONFIG = PROJECT_ROOT / "configs" / "claw_eval_deepseek.yaml"


def command(*args: str) -> str:
    """Read a command result without passing credentials as arguments."""
    return subprocess.check_output(list(args), text=True, stderr=subprocess.PIPE).strip()


def fingerprint() -> dict[str, str]:
    """Check all upstream files, including ignored files, except Git internals."""
    return {str(path.relative_to(UPSTREAM)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in UPSTREAM.rglob("*") if path.is_file() and ".git" not in path.relative_to(UPSTREAM).parts}


def validate_configuration(path: Path, settings: Settings,
                           extra_body: dict[str, Any] | None = None) -> Any:
    """Fail closed before native load_config can silently choose defaults."""
    if not path.is_file():
        raise S5Stop("pilot config file does not exist")
    from claw_eval.config import load_config
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or set(raw.get("judge", {})) - {"api_key", "base_url", "model_id", "enabled"}:
        raise S5Stop("unsupported judge config")
    config = load_config(path)
    if settings.base_url != "https://api.deepseek.com" or settings.agent_model != "deepseek-flash" or settings.judge_model != "deepseek-flash":
        raise S5Stop("pilot requires the approved DeepSeek endpoint/model")
    for role in (config.model, config.judge, config.user_agent_model):
        if role.api_key != settings.api_key or role.base_url != settings.base_url or role.model_id != "deepseek-flash":
            raise S5Stop("resolved config identity does not match approved settings")
    expected = extra_body if extra_body is not None else {"thinking": {"type": "disabled"}, "max_tokens": 1024}
    if config.model.extra_body != expected or not config.judge.enabled or not config.sandbox.enabled:
        raise S5Stop("pilot thinking, output cap, judge or sandbox configuration changed")
    return config


def preflight(config: Any) -> dict[str, Any]:
    """Verify local services and one disposable sandbox without LLM requests."""
    for port in (9100, 9103):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise S5Stop(f"mock service port {port} is already occupied") from None
    if "DOCKER_HOST" not in os.environ:
        os.environ["DOCKER_HOST"] = command("docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}")
    image_id = command("docker", "image", "inspect", "--format", "{{.Id}}", config.sandbox.image)
    from claw_eval.runner.sandbox_runner import SandboxRunner
    import httpx
    runner = SandboxRunner(config.sandbox)
    handle = runner.start_container(run_id="trajjudge-s5-preflight")
    try:
        with httpx.Client(trust_env=False, timeout=10) as client:
            health = client.get(handle.sandbox_url + "/health").json()
            execution = client.post(handle.sandbox_url + "/exec", json={"command": "echo S5_SANDBOX_READY"}).json()
        if health.get("status") != "ok" or execution.get("exit_code") != 0 or execution.get("stdout", "").strip() != "S5_SANDBOX_READY":
            raise S5Stop("sandbox preflight failed")
    finally:
        runner.stop_container(handle)
    return {"image_id": image_id, "health": "ok", "exec": "S5_SANDBOX_READY", "python": platform.python_version(),
            "openai_version": version("openai")}


def main(argv: list[str] | None = None) -> int:
    """Default to estimate only; --run authorizes the already-approved pilot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["ERROR_RATE"] = "0"
    for key in ("no_proxy", "NO_PROXY"):
        current = set(filter(None, os.environ.get(key, "").split(",")))
        os.environ[key] = ",".join(sorted(current | {"localhost", "127.0.0.1"}))
    settings = load_settings()
    os.environ["DEEPSEEK_API_KEY"] = settings.api_key
    config = validate_configuration(CONFIG, settings)
    if command("git", "-C", str(UPSTREAM), "rev-parse", "HEAD") != EXPECTED_COMMIT:
        raise S5Stop("Claw-Eval commit differs from the reviewed source")
    if command("git", "-C", str(UPSTREAM), "status", "--porcelain"):
        raise S5Stop("Claw-Eval worktree is dirty")
    from claw_eval.models.task import TaskDefinition
    for task_id, turns in TASKS.items():
        root = UPSTREAM / "tasks" / task_id
        task = TaskDefinition.from_yaml(root / "task.yaml")
        if "general" not in task.tags or task.user_agent.enabled or task.environment.max_turns != turns:
            raise S5Stop("task changed from the reviewed general-text whitelist")
        if any(not (root / file).is_file() for file in task.sandbox_files):
            raise S5Stop("required task fixture is missing")
    pricing = load_pricing(settings.pricing_file)
    if settings.judge_model not in pricing:
        raise S5Stop("verified pricing is required")
    before = summarize(LLMClient(settings).usage_log.read(), pricing)
    estimate = {"tasks": list(TASKS), "trials": 1, "parallel": 1, "estimated_usd_range": [0.03, 0.10],
                "batch_reserve_usd": 0.75, "stage_budget_usd": 3.0, "input_estimate_cap": INPUT_ESTIMATE_CAP,
                "agent_output_cap": 1024, "judge_output_cap": 8192, "attempt_limit": 3,
                "cumulative_usage_before": asdict(before)}
    print(json.dumps({"estimate": estimate}), flush=True)
    if not args.preflight and not args.run:
        return 0
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "pilot.json"
    if args.run and manifest_path.exists():
        raise S5Stop("pilot manifest already exists; refusing an extra trial or overwrite")
    original_files = fingerprint()
    infrastructure = preflight(config)
    (OUTPUT / "preflight.json").write_text(json.dumps(infrastructure, indent=2) + "\n")
    print(json.dumps({"preflight": infrastructure}), flush=True)
    if not args.run:
        if fingerprint() != original_files:
            raise S5Stop("upstream files changed during preflight")
        return 0
    if before.cost_usd is None:
        raise S5Stop("historical cost is unknown")
    ceiling = min(3.0, before.cost_usd + 0.75)
    os.environ["TRAJJUDGE_S5_CEILING"] = str(ceiling)
    if settings.judge_model not in LLMClient(settings, max_attempts=3, timeout=60).list_models():
        raise S5Stop("configured model is absent from model discovery")
    manifest: dict[str, Any] = {"timestamp": utc_now(), "status": "running", "estimate": estimate,
        "budget_ceiling_usd": ceiling, "claw_eval_commit": EXPECTED_COMMIT, "infrastructure": infrastructure,
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "pricing_sha256": hashlib.sha256(settings.pricing_file.read_bytes()).hexdigest(), "tasks": [],
        "deviations": ["DeepSeek agent and grader replace upstream model choices; not leaderboard-comparable",
                       "one trial; no Pass^3 estimate", "agent thinking disabled; judge thinking enabled with default effort",
                       "shared non-streaming transport replaces native streaming and layered retries",
                       "network timeout is 60 seconds instead of native provider 300 seconds",
                       "agent max_tokens=1024; judge max_tokens=8192; serial quotas and USD 0.75 reservation",
                       "input estimate cap raised from the provisional 16k to 48k after measuring native schema size",
                       "mock ERROR_RATE explicitly zero; implementation default preserved"]}
    def save() -> None:
        manifest["cumulative_usage"] = asdict(summarize(LLMClient(settings).usage_log.read(), pricing))
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    save()
    multiprocessing.set_start_method("spawn", force=True)
    from claw_eval import cli
    original_worker = cli._run_single_task
    cli._run_single_task = bounded_worker
    try:
        for task_id in TASKS:
            base = OUTPUT / task_id
            cli.main(["batch", "--tasks-dir", str(UPSTREAM / "tasks"), "--tag", "general", "--filter", task_id,
                      "--config", str(CONFIG), "--trials", "1", "--parallel", "1", "--sandbox",
                      "--sandbox-image", config.sandbox.image, "--trace-dir", str(base)])
            files = list(base.glob("*/batch_results.json"))
            if len(files) != 1:
                raise S5Stop("expected exactly one batch result for the task")
            records = json.loads(files[0].read_text())
            if len(records) != 1 or records[0].get("error") or len(records[0].get("trials", [])) != 1 or records[0]["trials"][0].get("error"):
                raise S5Stop("native task failed; refusing to continue or substitute tasks")
            trial = records[0]["trials"][0]
            if not Path(trial["trace"]).is_file():
                raise S5Stop("native trace is missing")
            manifest["tasks"].append({"task_id": task_id, "batch_results": str(files[0]), "trial": trial,
                                      "sidecar": str(files[0].parent / "s5_sidecar" / "requests.jsonl")})
            save()
        manifest["status"] = "complete"
    except BaseException as exc:
        manifest["status"] = "stopped"
        manifest["error_category"] = type(exc).__name__
        save()
        raise
    finally:
        cli._run_single_task = original_worker
        final_files = fingerprint()
        delta = sorted(key for key in original_files.keys() | final_files.keys() if original_files.get(key) != final_files.get(key))
        manifest["upstream_changed_paths"] = delta
        if delta:
            manifest["status"] = "stopped"
        save()
    print(json.dumps({"status": manifest["status"], "tasks": len(manifest["tasks"]), "cumulative_usage": manifest["cumulative_usage"]}), flush=True)
    return 0 if manifest["status"] == "complete" else 1
