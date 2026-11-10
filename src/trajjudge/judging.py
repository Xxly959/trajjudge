"""Configurable, repeatable, concurrent LLM-grader runs for stability (RQ2) and injection (RQ3).

One output row per (trace, grader, judge config, repeat). Every LLM call goes through the
shared client (cache keyed with repeat_id, ledger, budget). Rows are append-only JSONL and a
rerun skips rows that already exist, so interrupted batches resume without repaying.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from openjudge.evaluation_strategy import AverageEvaluationStrategy, VotingEvaluationStrategy
from openjudge.graders.agent import (ActionLoopDetectionGrader, ObservationInformationGainGrader,
                                     TrajectoryAccuracyGrader, TrajectoryComprehensiveGrader)
from openjudge.graders.schema import GraderScore

from .config import PROJECT_ROOT
from .artifacts import atomic_text
from .cache import make_key
from .llm import LLMClient, LLMError
from .openjudge_bridge import openjudge_model
from .perturb import defended_template
from .usage import utc_now

LLM_GRADERS = ("trajectory_accuracy", "trajectory_comprehensive")
RULE_GRADERS = ("action_loop_detection", "observation_information_gain")
SCALES = {"trajectory_accuracy": (1.0, 3.0), "trajectory_comprehensive": (0.0, 1.0),
          "action_loop_detection": (0.0, 1.0), "observation_information_gain": (0.0, 1.0)}
STRATEGIES = ("direct", "average", "voting")


@dataclass(frozen=True, slots=True)
class JudgeConfig:
    """One judge setup. ``num_evaluations`` is 1 for ``direct`` and >= 2 otherwise."""

    grader: str
    thinking: bool
    strategy: str = "direct"
    num_evaluations: int = 1
    max_tokens: int | None = None
    temperature: float | None = None
    defended: bool = False

    def __post_init__(self) -> None:
        if self.grader not in LLM_GRADERS or self.strategy not in STRATEGIES:
            raise ValueError("unknown LLM grader or strategy")
        if (self.strategy == "direct") != (self.num_evaluations == 1) or self.num_evaluations < 1:
            raise ValueError("direct needs num_evaluations == 1; average/voting need >= 2")

    @property
    def name(self) -> str:
        """Stable identifier used to group rows."""
        temp = "" if self.temperature is None else f"|t={self.temperature}"
        guard = "|def" if self.defended else ""
        return f"{self.grader}|think={'on' if self.thinking else 'off'}|{self.strategy}{self.num_evaluations}{temp}{guard}"

    @property
    def effective_max_tokens(self) -> int:
        """Completion cap; thinking tokens count against it, so thinking-on gets more room."""
        if self.max_tokens is not None:
            return self.max_tokens
        return 4096 if self.thinking else (1024 if self.grader == "trajectory_accuracy" else 3072)


def openjudge_commit() -> str:
    """Return the pinned OpenJudge checkout commit (graders are traceable by it)."""
    return subprocess.check_output(["git", "-C", str(PROJECT_ROOT.parent / "OpenJudge"), "rev-parse", "HEAD"], text=True).strip()


def _strategy(config: JudgeConfig) -> Any:
    if config.strategy == "average":
        return AverageEvaluationStrategy(num_evaluations=config.num_evaluations)
    if config.strategy == "voting":
        return VotingEvaluationStrategy(num_votes=config.num_evaluations)
    return None


def base_row(trace_id: str, config: JudgeConfig, judge_model: str | None, repeat_id: int, commit: str, **extra: Any) -> dict[str, Any]:
    """Fields every row carries."""
    return {"trace_id": trace_id, "grader": config.grader, "config": config.name, "score": None, "reason": "",
            "judge_model": judge_model, "thinking": config.thinking, "strategy": config.strategy,
            "num_evaluations": config.num_evaluations, "temperature": config.temperature,
            "max_tokens": config.effective_max_tokens, "defended": config.defended, "repeat_id": repeat_id, "openjudge_commit": commit,
            "timestamp": utc_now(), "usage": {}, "status": "ok", **extra}


def check_raw(grader: str, raw: dict[str, Any], *, expected_steps: int | None = None) -> None:
    """Reject raw model output the upstream grader would silently clamp or default."""
    if grader == "trajectory_accuracy":
        if type(raw.get("score")) not in (int, float) or raw["score"] not in (1, 2, 3):
            raise ValueError("accuracy score must be 1, 2 or 3")
        return
    steps = raw.get("step_evaluations")
    if not isinstance(steps, list) or not steps:
        raise ValueError("step_evaluations missing")
    if expected_steps is not None:
        indices = [s.get("step_index") for s in steps]
        if len(steps) != expected_steps or any(type(i) is not int for i in indices) or sorted(indices) != list(range(expected_steps)):
            raise ValueError("step evaluations must cover every assistant tool batch once")
    for step in steps:
        if not isinstance(step.get("step_reason"), str) or not step["step_reason"].strip():
            raise ValueError("step reason is missing")
        for key in ("contribution_score", "relevance_score", "accuracy_score", "efficiency_score"):
            if type(step.get(key)) is not int or not 1 <= step[key] <= 5:
                raise ValueError("step scores must be integers 1-5")


async def _grade(messages: list[dict[str, Any]], config: JudgeConfig, client: LLMClient, repeat_id: int, tag: str) -> tuple[Any, Any]:
    async with openjudge_model(client, thinking=config.thinking, max_tokens=config.effective_max_tokens, tag=tag,
                               repeat_id=repeat_id, temperature=config.temperature) as (model, bridge):
        cls = TrajectoryAccuracyGrader if config.grader == "trajectory_accuracy" else TrajectoryComprehensiveGrader
        template = defended_template(cls.DEFAULT_TEMPLATE) if config.defended else None
        result = await cls(model=model, strategy=_strategy(config), template=template).aevaluate(messages=messages)
        if bridge.failure:
            raise LLMError(bridge.failure)
        return result, bridge


def judge_once(trace_id: str, messages: list[dict[str, Any]], config: JudgeConfig, client: LLMClient,
               repeat_id: int, commit: str, variant: str = "original", phase: str = "p3") -> dict[str, Any]:
    """Grade one trajectory once; failures become error rows with a null score, never zeros."""
    row = base_row(trace_id, config, client.settings.judge_model, repeat_id, commit, variant=variant)
    tag = f"{phase}/{trace_id}/{variant}/{config.name}/{repeat_id}"
    try:
        result, bridge = asyncio.run(_grade(messages, config, client, repeat_id, tag))
    except LLMError as exc:
        return {**row, "status": "error", "reason": str(exc), "fatal": True}
    except Exception as exc:  # grader/parse failure: keep the row explicit
        return {**row, "status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
    results = bridge.results
    row["usage"] = {"api_calls": sum(not r.cached for r in results), "cached_calls": sum(r.cached for r in results),
                    "prompt_tokens": sum(r.prompt_tokens for r in results),
                    "completion_tokens": sum(r.completion_tokens for r in results)}
    low, high = SCALES[config.grader]
    if not isinstance(result, GraderScore) or not math.isfinite(result.score) or not low <= result.score <= high or not result.reason.strip():
        return {**row, "status": "error", "reason": f"no valid score: {getattr(result, 'error', result)!s}"[:300]}
    if len(results) != config.num_evaluations or any(
            not r.raw_response.get("choices") or r.raw_response["choices"][0].get("finish_reason") != "stop" for r in results):
        return {**row, "status": "error", "reason": "incomplete completions or wrong number of evaluations"}
    try:
        for completion in results:
            check_raw(config.grader, json.loads(completion.text), expected_steps=sum(
                bool(m.get("tool_calls")) for m in messages if m.get("role") == "assistant"))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {**row, "status": "error", "reason": f"raw verdict invalid (upstream may have clamped it): {exc}"[:300]}
    row.update(score=float(result.score), reason=result.reason)
    return row


def rule_row(trace_id: str, messages: list[dict[str, Any]], name: str, commit: str, variant: str = "original") -> dict[str, Any]:
    """Run one rule-based grader (deterministic, free)."""
    cls = ActionLoopDetectionGrader if name == "action_loop_detection" else ObservationInformationGainGrader
    result = asyncio.run(cls().aevaluate(messages=messages))
    row = {"trace_id": trace_id, "grader": name, "config": f"{name}|rule", "score": float(result.score), "reason": result.reason,
           "judge_model": None, "thinking": None, "strategy": "rule", "num_evaluations": 0, "temperature": None,
           "max_tokens": None, "repeat_id": 0, "openjudge_commit": commit, "timestamp": utc_now(), "usage": {},
           "status": "ok", "variant": variant}
    return row


def row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Identity of a row for resume logic."""
    if row.get("job_id"):
        return ("job", row["job_id"])
    return (row["trace_id"], row.get("variant", "original"), row["config"], row["repeat_id"],
            row.get("judge_model"), row.get("max_tokens"), row.get("openjudge_commit"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Read a rows JSONL (missing file -> empty)."""
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last row per key, so a retried error row is superseded by its successful rerun."""
    return list({row_key(r): r for r in rows}.values())


def run_jobs(jobs: Sequence[tuple[str, list[dict[str, Any]], JudgeConfig, int, str]], client: LLMClient, output: Path,
             *, workers: int = 8, run_dir: Path | None = None, phase: str = "p3") -> dict[str, int]:
    """Run (trace_id, messages, config, repeat_id, variant) jobs concurrently, appending rows to ``output``.

    Existing ok rows are skipped (error rows are retried; use ``latest_rows`` to read). A fatal (budget) error stops scheduling new jobs.
    """
    commit = openjudge_commit()
    descriptors = [{"trace_id": j[0], "input_sha256": make_key({"messages": j[1]}),
                    "config": asdict(j[2]), "max_tokens": j[2].effective_max_tokens,
                    "repeat_id": j[3], "variant": j[4]} for j in jobs]
    keys = [make_key(d) for d in descriptors]
    logical_keys = [(j[0], j[4], j[2].name, j[3]) for j in jobs]
    if len(set(logical_keys)) != len(jobs):
        raise ValueError("duplicate experiment jobs")
    plan = {"schema": 1, "phase": phase, "model": client.settings.judge_model, "base_url": client.settings.base_url,
            "openjudge_commit": commit, "jobs": sorted(descriptors, key=make_key)}
    identity = make_key(plan)
    run_dir = run_dir or output.parent / "runs" / output.stem
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    active = run_dir / "active.lock"
    try:
        lock_fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("run is active or interrupted; inspect active.lock and process state before resuming") from None
    os.close(lock_fd)
    try:
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest["identity"] != identity:
                raise ValueError("run manifest identity changed; use a new run directory and output")
        elif output.exists():
            raise ValueError("existing output has no identity manifest; preserve and migrate explicitly")
        stored = {}
        for key in keys:
            path = run_dir / "rows" / f"{key}.json"
            if path.exists():
                row = json.loads(path.read_text())
                if row.get("job_id") != key:
                    raise ValueError("atomic row identity mismatch")
                stored[key] = row
        return _run_checkpointed(jobs, client, output, workers, run_dir, plan, identity, keys, stored, commit, phase)
    finally:
        active.unlink(missing_ok=True)


def _run_checkpointed(jobs: Sequence[Any], client: LLMClient, output: Path, workers: int,
                      run_dir: Path, plan: dict[str, Any], identity: str, keys: list[str],
                      stored: dict[str, Any], commit: str, phase: str) -> dict[str, int]:
    """Run under the exclusive run lock; per-job files are authoritative on recovery."""
    def checkpoint() -> None:
        atomic_text(output, "".join(json.dumps(stored[k], ensure_ascii=False, allow_nan=False) + "\n"
                                   for k in keys if k in stored))
        completed = [k for k in keys if k in stored and stored[k]["status"] == "ok"]
        atomic_text(run_dir / "manifest.json", json.dumps({"identity": identity, "plan": plan,
            "total_jobs": len(jobs), "completed": completed, "updated_at": utc_now()}, indent=2))

    checkpoint()
    lock, stop = threading.Lock(), threading.Event()
    counts = {"run": 0, "skipped": 0, "error": 0}

    def work(item: tuple[str, Any]) -> None:
        key, job = item
        trace_id, messages, config, repeat_id, variant = job
        if stop.is_set():
            return
        row = judge_once(trace_id, messages, config, client, repeat_id, commit, variant, phase)
        row["job_id"] = key
        with lock:
            atomic_text(run_dir / "rows" / f"{key}.json", json.dumps(row, ensure_ascii=False, allow_nan=False))
            stored[key] = row
            checkpoint()
            counts["run"] += 1
            counts["error"] += row["status"] != "ok"
        if row.get("fatal"):
            stop.set()

    todo = []
    for key, job in zip(keys, jobs):
        if key in stored and stored[key]["status"] == "ok":
            counts["skipped"] += 1
        else:
            todo.append((key, job))
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, todo))
    counts["stopped_early"] = int(stop.is_set())
    return counts


def estimate_cost(n_calls: int, avg_prompt: int, avg_completion: int, *, input_per_mtok: float = 0.30,
                  output_per_mtok: float = 1.20) -> float:
    """Peak cache-miss USD estimate for ``n_calls`` completions."""
    return n_calls * (avg_prompt * input_per_mtok + avg_completion * output_per_mtok) / 1_000_000


def configs_grid(graders: Iterable[str], thinking: Iterable[bool], strategies: Iterable[tuple[str, int]]) -> list[JudgeConfig]:
    """Cartesian product of judge configs."""
    return [JudgeConfig(g, t, s, n) for g in graders for t in thinking for s, n in strategies]
