"""Deterministic, category-stratified selection of Claw-Eval tasks for P2."""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import yaml

EXCLUDED_SERVICE_MARKERS = ("web_real", "ocr", "caption")


def is_candidate(task: Mapping[str, Any], *, max_turns: int, task_dir: Path | None = None) -> bool:
    """Return True for text-only general tasks that run on local mock services.

    Excludes user-agent tasks, multimodal tasks, real-network or OCR services,
    compaction/todo runtime modes, missing fixtures and tasks above ``max_turns``.
    """
    if "general" not in (task.get("tags") or []) or (task.get("user_agent") or {}).get("enabled"):
        return False
    env = task.get("environment") or {}
    if env.get("enable_compact") or env.get("enable_todo") or int(env.get("max_turns", 10**6)) > max_turns:
        return False
    for service in task.get("services") or []:
        text = f"{service.get('name', '')} {service.get('command', '')}"
        if any(marker in text for marker in EXCLUDED_SERVICE_MARKERS):
            return False
    if task_dir is not None:
        if not (task_dir / "grader.py").is_file() and not task.get("judge_rubric"):
            return False
        if any(not (task_dir / name).is_file() for name in task.get("sandbox_files") or []):
            return False
    return True


def load_candidates(tasks_dir: Path, *, max_turns: int) -> list[dict[str, Any]]:
    """Read all task.yaml files and keep candidates, sorted by task id."""
    found = []
    for path in sorted(Path(tasks_dir).glob("*/task.yaml")):
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        if is_candidate(task, max_turns=max_turns, task_dir=path.parent):
            found.append({"task_id": task["task_id"], "category": task.get("category", "unknown"),
                          "difficulty": task.get("difficulty", "unknown"),
                          "max_turns": int(task["environment"]["max_turns"])})
    return found


def stratified_sample(candidates: list[dict[str, Any]], quotas: Mapping[str, int], *, seed: int) -> list[dict[str, Any]]:
    """Pick ``quotas[difficulty]`` tasks per difficulty, round-robin over categories.

    Args:
        candidates: Rows with ``task_id``, ``category`` and ``difficulty``.
        quotas: Tasks wanted per difficulty (capped by availability).
        seed: Shuffle seed; the result is a pure function of the inputs.
    """
    rng = random.Random(seed)
    chosen: list[dict[str, Any]] = []
    for difficulty, want in quotas.items():
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in sorted(candidates, key=lambda r: r["task_id"]):
            if row["difficulty"] == difficulty:
                groups[row["category"]].append(row)
        for rows in groups.values():
            rng.shuffle(rows)
        order = sorted(groups)
        rng.shuffle(order)
        taken = 0
        while taken < want and any(groups.values()):
            for category in order:
                if groups[category] and taken < want:
                    chosen.append(groups[category].pop(0))
                    taken += 1
    return chosen


def select_for_annotation(rows: list[dict[str, Any]], count: int, *, seed: int, max_fail_share: float = 0.6) -> list[dict[str, Any]]:
    """Choose ``count`` trajectories to annotate, over-sampling official failures.

    Rows need ``trace_id``, ``category``, ``config`` and ``passed`` (official pass flag).
    Official failures are taken first (up to ``max_fail_share`` of ``count``), alternating agent
    configs; the rest are official passes drawn round-robin over categories. Pure function of inputs.
    """
    rng = random.Random(seed)
    ordered = sorted(rows, key=lambda r: r["trace_id"])
    rng.shuffle(ordered)

    def round_robin(pool: list[dict[str, Any]], want: int) -> list[dict[str, Any]]:
        buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in pool:
            buckets[(row["category"], row["config"])].append(row)
        keys = sorted(buckets)
        picked: list[dict[str, Any]] = []
        while len(picked) < want and any(buckets.values()):
            for key in keys:
                if buckets[key] and len(picked) < want:
                    picked.append(buckets[key].pop())
        return picked

    fails = round_robin([r for r in ordered if not r["passed"]], int(count * max_fail_share))
    chosen_ids = {r["trace_id"] for r in fails}
    passes = round_robin([r for r in ordered if r["passed"] and r["trace_id"] not in chosen_ids], count - len(fails))
    return fails + passes
