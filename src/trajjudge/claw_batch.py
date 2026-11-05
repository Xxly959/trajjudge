"""Budget-capped, resumable Claw-Eval runs for P2 (one trial per task and config).

Reuses the audited S5 bindings (shared LLM client, ledger, request quotas) with a
run profile instead of the two-task whitelist. A per-task failure is recorded and
the run continues; a budget stop aborts everything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .claw_bridge import S5Stop, bounded_worker
from .claw_pilot import EXPECTED_COMMIT, UPSTREAM, command, fingerprint, preflight, validate_configuration
from .config import PROJECT_ROOT, load_settings
from .llm import LLMClient
from .usage import load_pricing, summarize, utc_now

CONFIGS = {
    "flash-think-off": ("configs/claw_p2_off.yaml", {"thinking": {"type": "disabled"}, "max_tokens": 4096}, False, 4096),
    "flash-think-on": ("configs/claw_p2_on.yaml", {"thinking": {"type": "enabled"}, "max_tokens": 16384}, True, 16384),
}
OUTPUT = PROJECT_ROOT / "outputs" / "claw_eval" / "p2"
INPUT_CAP_BYTES = 200_000
JUDGE_QUOTA = 8


def ambiguous_filters(task_ids: list[str], all_ids: list[str]) -> list[str]:
    """Return chosen ids that substring-match another task (native ``--filter`` is a substring match)."""
    return [t for t in task_ids if sum(t.lower() in other.lower() for other in all_ids) != 1]


def completed_tasks(manifest: Path) -> set[str]:
    """Task ids already recorded as complete in a manifest JSONL."""
    if not manifest.is_file():
        return set()
    rows = (json.loads(line) for line in manifest.read_text().splitlines() if line.strip())
    return {row["task_id"] for row in rows if row.get("status") == "complete"}


def main(argv: list[str] | None = None) -> int:
    """Estimate by default; ``--run`` executes the selected tasks under ``--stage-cap-usd``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=sorted(CONFIGS), required=True)
    parser.add_argument("--tasks-file", default="configs/p2_tasks.json")
    parser.add_argument("--only", nargs="*", default=None, help="restrict to these task ids")
    parser.add_argument("--exclude", nargs="*", default=[], help="task ids to skip (e.g. runaway tasks)")
    parser.add_argument("--stage-cap-usd", type=float, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["ERROR_RATE"] = "0"
    for key in ("no_proxy", "NO_PROXY"):
        current = set(filter(None, os.environ.get(key, "").split(",")))
        os.environ[key] = ",".join(sorted(current | {"localhost", "127.0.0.1"}))
    settings = load_settings()
    os.environ["DEEPSEEK_API_KEY"] = settings.api_key
    config_rel, extra_body, thinking, agent_cap = CONFIGS[args.config]
    config_path = PROJECT_ROOT / config_rel
    config = validate_configuration(config_path, settings, extra_body)
    if command("git", "-C", str(UPSTREAM), "rev-parse", "HEAD") != EXPECTED_COMMIT or command("git", "-C", str(UPSTREAM), "status", "--porcelain"):
        raise S5Stop("Claw-Eval differs from the reviewed clean checkout")
    selected = json.loads((PROJECT_ROOT / args.tasks_file).read_text())
    tasks = {row["task_id"]: row["max_turns"] for row in selected if (args.only is None or row["task_id"] in args.only) and row["task_id"] not in args.exclude}
    all_ids = [p.name for p in (UPSTREAM / "tasks").iterdir() if p.is_dir()]
    if bad := ambiguous_filters(list(tasks), all_ids):
        raise S5Stop(f"ambiguous native filter for {bad}")
    run_dir = OUTPUT / args.config
    manifest = run_dir / "manifest.jsonl"
    todo = [t for t in tasks if t not in completed_tasks(manifest)]
    pricing = load_pricing(settings.pricing_file)
    before = summarize(LLMClient(settings).usage_log.read(), pricing)
    if before.cost_usd is None:
        raise S5Stop("historical cost is unknown")
    ceiling = before.cost_usd + args.stage_cap_usd  # the explicit, owner-approved stage cap replaces the phase-1 USD 3 ceiling
    print(json.dumps({"config": args.config, "tasks_total": len(tasks), "tasks_todo": len(todo),
                      "stage_cap_usd": args.stage_cap_usd, "ceiling_usd": ceiling,
                      "spent_before_usd": before.cost_usd}), flush=True)
    if not args.run or not todo:
        return 0
    run_dir.mkdir(parents=True, exist_ok=True)
    original_files = fingerprint()
    infrastructure = preflight(config)
    profile = {"tasks": {t: tasks[t] for t in todo}, "agent_thinking": thinking, "agent_cap": agent_cap,
               "judge_quota": JUDGE_QUOTA, "input_cap": INPUT_CAP_BYTES, "tag_prefix": f"p2/{args.config}"}
    profile_path = run_dir / "profile.json"
    profile_path.write_text(json.dumps(profile, indent=2) + "\n")
    os.environ["TRAJJUDGE_CLAW_PROFILE"] = str(profile_path)
    os.environ["TRAJJUDGE_S5_CEILING"] = str(ceiling)
    multiprocessing.set_start_method("spawn", force=True)
    from claw_eval import cli
    original_worker = cli._run_single_task
    cli._run_single_task = bounded_worker
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    stop_all = False
    try:
        for task_id in todo:
            row: dict[str, Any] = {"task_id": task_id, "config": args.config, "timestamp": utc_now(),
                                   "claw_eval_commit": EXPECTED_COMMIT, "config_sha256": config_sha,
                                   "image_id": infrastructure["image_id"], "status": "stopped"}
            base = run_dir / task_id
            try:
                cli.main(["batch", "--tasks-dir", str(UPSTREAM / "tasks"), "--tag", "general", "--filter", task_id,
                          "--config", str(config_path), "--trials", "1", "--parallel", "1", "--sandbox",
                          "--sandbox-image", config.sandbox.image, "--trace-dir", str(base)])
                files = list(base.glob("*/batch_results.json"))
                records = json.loads(files[0].read_text()) if len(files) == 1 else []
                trial = records[0]["trials"][0] if len(records) == 1 and records[0].get("trials") else {}
                if records and not records[0].get("error") and trial and not trial.get("error") and Path(trial["trace"]).is_file():
                    row.update(status="complete", trace=trial["trace"], batch_results=str(files[0]),
                               sidecar=str(files[0].parent / "s5_sidecar" / "requests.jsonl"), trial=trial)
                else:
                    row["reason"] = "native result missing or errored"
            except (S5Stop, SystemExit, Exception) as exc:
                row["reason"] = f"{type(exc).__name__}: {exc}"[:300]
                stop_all = isinstance(exc, S5Stop) and "budget" in str(exc).lower()
            row["cumulative_cost_usd"] = summarize(LLMClient(settings).usage_log.read(), pricing).cost_usd
            with manifest.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(json.dumps({k: row.get(k) for k in ("task_id", "status", "reason", "cumulative_cost_usd")}), flush=True)
            if stop_all:
                break
    finally:
        cli._run_single_task = original_worker
        final_files = fingerprint()
        delta = sorted(key for key in original_files.keys() | final_files.keys() if original_files.get(key) != final_files.get(key))
        if delta:
            print(json.dumps({"upstream_changed_paths": delta}))
    after = summarize(LLMClient(settings).usage_log.read(), pricing)
    print(json.dumps({"summary": asdict(after), "spent_this_run_usd": (after.cost_usd or 0) - before.cost_usd}), flush=True)
    return 1 if stop_all or delta else 0
