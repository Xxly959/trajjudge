"""Offline tests for repeatable judge runs; mock verdicts are not experimental results."""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from trajjudge.adapter import adapt_trace
from trajjudge.config import Settings
from trajjudge.judging import JudgeConfig, load_rows, rule_row, run_jobs
from trajjudge.llm import LLMClient

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"
COMMIT = "0" * 40


def reply(score: int) -> dict[str, Any]:
    body = json.dumps({"score": score, "reason": "synthetic"})
    return {"id": "m", "object": "chat.completion", "created": 1, "model": "judge-test",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": body}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}


class Transport:
    def __init__(self, scores: list[int]) -> None:
        self.scores, self.requests, self.lock = scores, [], threading.Lock()

    def __call__(self, request: dict[str, Any]) -> Any:
        with self.lock:
            self.requests.append(request)
            return reply(self.scores[(len(self.requests) - 1) % len(self.scores)])


@pytest.fixture
def messages() -> list[dict[str, Any]]:
    return adapt_trace(FIXTURES / "contact.jsonl", sidecar_path=FIXTURES / "contact.sidecar.jsonl").messages


def test_config_validation_and_name() -> None:
    assert JudgeConfig("trajectory_accuracy", True, "voting", 3).name == "trajectory_accuracy|think=on|voting3"
    with pytest.raises(ValueError):
        JudgeConfig("trajectory_accuracy", True, "direct", 3)
    with pytest.raises(ValueError):
        JudgeConfig("trajectory_accuracy", True, "average", 1)
    assert JudgeConfig("trajectory_accuracy", True).effective_max_tokens > JudgeConfig("trajectory_accuracy", False).effective_max_tokens


def test_repeats_are_real_requests_and_rows_are_complete(settings: Settings, tmp_path: Path, messages: list[dict[str, Any]]) -> None:
    transport = Transport([3, 2, 1])
    client = LLMClient(settings, transport=transport)
    cfg = JudgeConfig("trajectory_accuracy", False)
    jobs = [("t1", messages, cfg, r, "original") for r in range(3)]
    out = tmp_path / "rows.jsonl"
    assert run_jobs(jobs, client, out, workers=3)["run"] == 3
    rows = load_rows(out)
    assert len(transport.requests) == 3
    assert sorted(r["score"] for r in rows) == [1.0, 2.0, 3.0]
    required = {"trace_id", "grader", "score", "reason", "judge_model", "thinking", "openjudge_commit",
                "timestamp", "usage", "repeat_id", "strategy", "num_evaluations", "status"}
    assert all(required <= set(r) for r in rows) and {r["repeat_id"] for r in rows} == {0, 1, 2}
    again = run_jobs(jobs, client, out, workers=3)
    assert again["skipped"] == 3 and again["run"] == 0 and len(transport.requests) == 3


def test_voting_makes_n_distinct_calls_and_replays_from_cache(settings: Settings, tmp_path: Path, messages: list[dict[str, Any]]) -> None:
    transport = Transport([3, 3, 1])
    client = LLMClient(settings, transport=transport)
    cfg = JudgeConfig("trajectory_accuracy", True, "voting", 3)
    out = tmp_path / "rows.jsonl"
    run_jobs([("t1", messages, cfg, 0, "original")], client, out, workers=1)
    row = load_rows(out)[0]
    assert len(transport.requests) == 3 and row["score"] == 3.0 and row["usage"]["api_calls"] == 3
    assert all(r["extra_body"] == {"thinking": {"type": "enabled"}} for r in transport.requests)
    out2 = tmp_path / "rows2.jsonl"
    run_jobs([("t1", messages, cfg, 0, "original")], LLMClient(settings, transport=transport), out2, workers=1)
    assert len(transport.requests) == 3 and load_rows(out2)[0]["usage"]["cached_calls"] == 3


def test_invalid_verdict_is_error_row_not_zero(settings: Settings, tmp_path: Path, messages: list[dict[str, Any]]) -> None:
    client = LLMClient(settings, transport=Transport([99]))
    out = tmp_path / "rows.jsonl"
    run_jobs([("t1", messages, JudgeConfig("trajectory_accuracy", False), 0, "original")], client, out, workers=1)
    row = load_rows(out)[0]
    assert row["status"] == "error" and row["score"] is None


def test_rule_graders_need_no_model(messages: list[dict[str, Any]]) -> None:
    row = rule_row("t1", messages, "action_loop_detection", COMMIT)
    assert row["judge_model"] is None and row["status"] == "ok" and 0.0 <= row["score"] <= 1.0


def test_defended_config_changes_prompt_and_cache_identity(settings: Settings, tmp_path: Path, messages: list[dict[str, Any]]) -> None:
    transport = Transport([3])
    client = LLMClient(settings, transport=transport)
    out = tmp_path / "rows.jsonl"
    plain, guarded = JudgeConfig("trajectory_accuracy", False), JudgeConfig("trajectory_accuracy", False, defended=True)
    assert plain.name != guarded.name
    run_jobs([("t", messages, plain, 0, "original"), ("t", messages, guarded, 0, "original")], client, out, workers=1)
    assert len(transport.requests) == 2
    texts = ["".join(str(m["content"]) for m in r["messages"]) for r in transport.requests]
    assert sum("untrusted data" in t for t in texts) == 1
    assert {r["defended"] for r in load_rows(out)} == {False, True}


@pytest.mark.parametrize("change", ["model", "messages", "cap"])
def test_resume_rejects_changed_experiment(change, settings, tmp_path, messages) -> None:
    transport = Transport([3])
    cfg = JudgeConfig("trajectory_accuracy", False)
    output = tmp_path / "rows.jsonl"
    run_jobs([("t", messages, cfg, 0, "original")], LLMClient(settings, transport=transport), output, workers=1)
    if change == "model":
        settings = replace(settings, judge_model="other-model")
    elif change == "cap":
        cfg = replace(cfg, max_tokens=2048)
    else:
        messages = [*messages, {"role": "assistant", "content": "changed evidence"}]
    with pytest.raises(ValueError, match="manifest|identity|changed"):
        run_jobs([("t", messages, cfg, 0, "original")], LLMClient(settings, transport=transport), output, workers=1)
    assert len(transport.requests) == 1


def test_comprehensive_requires_complete_step_coverage() -> None:
    from trajjudge.judging import check_raw
    step = {"step_index": 0, "step_reason": "synthetic", **{k: 5 for k in
            ("contribution_score", "relevance_score", "accuracy_score", "efficiency_score")}}
    with pytest.raises(ValueError, match="step"):
        check_raw("trajectory_comprehensive", {"step_evaluations": [step]}, expected_steps=2)


def test_resume_reconstructs_projection_from_atomic_rows(settings, tmp_path, messages) -> None:
    transport = Transport([3])
    output = tmp_path / "rows.jsonl"
    jobs = [("t", messages, JudgeConfig("trajectory_accuracy", False), 0, "original")]
    client = LLMClient(settings, transport=transport)
    run_jobs(jobs, client, output, workers=1)
    output.write_text('{"truncated":')
    assert run_jobs(jobs, client, output, workers=1)["skipped"] == 1
    assert load_rows(output)[0]["score"] == 3 and len(transport.requests) == 1


def test_duplicate_jobs_rejected_before_calls(settings, tmp_path, messages) -> None:
    transport = Transport([3])
    job = ("t", messages, JudgeConfig("trajectory_accuracy", False), 0, "original")
    with pytest.raises(ValueError, match="duplicate"):
        run_jobs([job, job], LLMClient(settings, transport=transport), tmp_path / "rows.jsonl", workers=2)
    assert not transport.requests
