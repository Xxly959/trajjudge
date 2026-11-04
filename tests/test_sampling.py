"""Offline tests for P2 task selection and batch helpers."""

from __future__ import annotations

import json
from pathlib import Path

from trajjudge.claw_batch import ambiguous_filters, completed_tasks
from trajjudge.sampling import is_candidate, stratified_sample

BASE = {"tags": ["general"], "environment": {"max_turns": 20}, "judge_rubric": "x", "services": [{"name": "gmail", "command": "python s.py"}]}


def test_candidate_filters() -> None:
    assert is_candidate(BASE, max_turns=30)
    assert not is_candidate({**BASE, "tags": ["multimodal"]}, max_turns=30)
    assert not is_candidate({**BASE, "user_agent": {"enabled": True}}, max_turns=30)
    assert not is_candidate({**BASE, "environment": {"max_turns": 50}}, max_turns=30)
    assert not is_candidate({**BASE, "services": [{"name": "web_real", "command": "x"}]}, max_turns=30)
    assert not is_candidate({**BASE, "environment": {"max_turns": 5, "enable_todo": True}}, max_turns=30)


def test_stratified_sample_is_deterministic_and_balanced() -> None:
    pool = [{"task_id": f"{c}{d}{i}", "category": c, "difficulty": d} for c in "abc" for d in ("hard", "easy") for i in range(3)]
    first = stratified_sample(pool, {"hard": 3, "easy": 3}, seed=1)
    assert first == stratified_sample(pool, {"hard": 3, "easy": 3}, seed=1)
    assert sorted({r["category"] for r in first if r["difficulty"] == "hard"}) == ["a", "b", "c"]
    assert len({r["task_id"] for r in first}) == 6
    assert len(stratified_sample(pool, {"hard": 99}, seed=1)) == 9


def test_ambiguous_filters_and_resume(tmp_path: Path) -> None:
    ids = ["T1_a", "T1_a_v2", "T2_b"]
    assert ambiguous_filters(["T1_a", "T2_b"], ids) == ["T1_a"]
    manifest = tmp_path / "m.jsonl"
    manifest.write_text("".join(json.dumps(r) + "\n" for r in [{"task_id": "x", "status": "complete"}, {"task_id": "y", "status": "stopped"}]))
    assert completed_tasks(manifest) == {"x"}
    assert completed_tasks(tmp_path / "none") == set()
