"""Configurable, repeatable, concurrent LLM-grader runs for stability (RQ2) and injection (RQ3).

One output row per (trace, grader, judge config, repeat). Every LLM call goes through the
shared client (cache keyed with repeat_id, ledger, budget). Rows are append-only JSONL and a
rerun skips rows that already exist, so interrupted batches resume without repaying.
"""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from openjudge.evaluation_strategy import AverageEvaluationStrategy, VotingEvaluationStrategy
from openjudge.graders.agent import (ActionLoopDetectionGrader, ObservationInformationGainGrader,
                                     TrajectoryAccuracyGrader, TrajectoryComprehensiveGrader)
from openjudge.graders.schema import GraderScore

from .config import PROJECT_ROOT
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


def check_raw(grader: str, raw: dict[str, Any]) -> None:
    """Reject raw model output the upstream grader would silently clamp or default."""
    if grader == "trajectory_accuracy":
        if type(raw.get("score")) not in (int, float) or raw["score"] not in (1, 2, 3):
            raise ValueError("accuracy score must be 1, 2 or 3")
        return
    steps = raw.get("step_evaluations")
    if not isinstance(steps, list) or not steps:
        raise ValueError("step_evaluations missing")
    for step in steps:
        for key in ("contribution_score", "relevance_score", "accuracy_score", "efficiency_score"):
            if type(step.get(key)) is not int or not 1 <= step[key] <= 5:
                raise ValueError("step scores must be integers 1-5")


async def _grade(messages: list[dict[str, Any]], config: JudgeConfig, client: LLMClient, repeat_id: int, tag: str) -> tuple[Any, Any]:
    async with openjudge_model(client, thinking=config.thinking, max_tokens=config.effective_max_tokens, tag=tag,
                               repeat_id=repeat_id, temperature=config.temperature) as (model, bridge):
        cls = TrajectoryAccuracyGrader if config.grader == "trajectory_accuracy" else TrajectoryComprehensiveGrader
        template = defended_template(cls.DEFAULT_TEMPLATE) if config.defended else None
        result = await cls(model=model, strategy=_strategy(config), template=template).aevaluate(messages=messages)
        return result, bridge


def judge_once(trace_id: str, messages: list[dict[str, Any]], config: JudgeConfig, client: LLMClient,
               repeat_id: int, commit: str, variant: str = "original") -> dict[str, Any]:
    """Grade one trajectory once; failures become error rows with a null score, never zeros."""
    row = base_row(trace_id, config, client.settings.judge_model, repeat_id, commit, variant=variant)
    tag = f"p3/{trace_id}/{variant}/{config.name}/{repeat_id}"
    try:
        result, bridge = asyncio.run(_grade(messages, config, client, repeat_id, tag))
    except LLMError as exc:
        return {**row, "status": "error", "reason": str(exc), "fatal": "budget" in str(exc).lower()}
    except Exception as exc:  # grader/parse failure: keep the row explicit
        return {**row, "status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}
    results = bridge.results
    row["usage"] = {"api_calls": sum(not r.cached for r in results), "cached_calls": sum(r.cached for r in results),
                    "prompt_tokens": sum(r.prompt_tokens for r in results),
                    "completion_tokens": sum(r.completion_tokens for r in results)}
    low, high = SCALES[config.grader]
    if not isinstance(result, GraderScore) or not math.isfinite(result.score) or not low <= result.score <= high:
        return {**row, "status": "error", "reason": f"no valid score: {getattr(result, 'error', result)!s}"[:300]}
    if len(results) != config.num_evaluations or any(
            not r.raw_response.get("choices") or r.raw_response["choices"][0].get("finish_reason") != "stop" for r in results):
        return {**row, "status": "error", "reason": "incomplete completions or wrong number of evaluations"}
    try:
        for completion in results:
            check_raw(config.grader, json.loads(completion.text))
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


def row_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    """Identity of a row for resume logic."""
    return (row["trace_id"], row.get("variant", "original"), row["config"], row["repeat_id"])


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Read a rows JSONL (missing file -> empty)."""
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last row per key, so a retried error row is superseded by its successful rerun."""
    return list({row_key(r): r for r in rows}.values())


def run_jobs(jobs: Sequence[tuple[str, list[dict[str, Any]], JudgeConfig, int, str]], client: LLMClient, output: Path,
             *, workers: int = 8) -> dict[str, int]:
    """Run (trace_id, messages, config, repeat_id, variant) jobs concurrently, appending rows to ``output``.

    Existing ok rows are skipped (error rows are retried; use ``latest_rows`` to read). A fatal (budget) error stops scheduling new jobs.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    done = {row_key(r) for r in load_rows(output) if r["status"] == "ok"}
    commit = openjudge_commit()
    lock, stop = threading.Lock(), threading.Event()
    counts = {"run": 0, "skipped": 0, "error": 0}

    def work(job: tuple[str, list[dict[str, Any]], JudgeConfig, int, str]) -> None:
        trace_id, messages, config, repeat_id, variant = job
        if stop.is_set():
            return
        row = judge_once(trace_id, messages, config, client, repeat_id, commit, variant)
        with lock:
            with output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            counts["run"] += 1
            counts["error"] += row["status"] != "ok"
        if row.get("fatal"):
            stop.set()

    todo = []
    for job in jobs:
        probe = {"trace_id": job[0], "variant": job[4], "config": job[2].name, "repeat_id": job[3]}
        if row_key(probe) in done:
            counts["skipped"] += 1
        else:
            todo.append(job)
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
