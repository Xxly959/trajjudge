"""Offline four-grader pipeline checks; fake verdicts are not human labels."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from trajjudge.adapter import adapt_trace
from trajjudge.config import Settings
from trajjudge.llm import LLMClient

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"


def test_offline_replay_survives_unrelated_later_unknown_cost(settings: Settings, tmp_path: Path) -> None:
    from dataclasses import replace
    from trajjudge.runner import run_graders
    from trajjudge.usage import UsageRecord, utc_now
    responses = [reply({"score": 2, "reason": "Synthetic mock"}), reply(evaluations())]
    requests = []
    def transport(request):
        requests.append(request)
        return responses.pop(0)
    client = LLMClient(settings, transport=transport)
    assert all(r.status == "ok" for r in run_graders([trace()], client))
    client.usage_log.append(UsageRecord(timestamp=utc_now(), tag="unrelated/later-stage", model="judge-test",
        thinking=False, prompt_tokens=0, completion_tokens=0, latency_ms=1, cached=False,
        status="unknown", usage_known=False))
    replay = run_graders([trace()], LLMClient(replace(settings, budget_usd=.00000001), offline=True))
    assert len(replay) == 4 and all(r.status == "ok" for r in replay)
    assert sum(r.usage["api_calls"] for r in replay) == 0
    assert sum(r.usage["cached_calls"] for r in replay) == 2
    assert len(requests) == 2


def reply(body: dict[str, Any]) -> dict[str, Any]:
    return {"id":"mock", "object":"chat.completion", "created":1, "model":"judge-test",
            "choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":json.dumps(body)}}],
            "usage":{"prompt_tokens":100,"completion_tokens":30,"total_tokens":130}}


def evaluations(count: int = 2) -> dict[str, Any]:
    return {"step_evaluations":[{"step_index":i,"step_reason":"Synthetic fixture verdict",
        "contribution_score":5,"relevance_score":5,"accuracy_score":5,"efficiency_score":5} for i in range(count)]}


def trace() -> Any:
    return adapt_trace(FIXTURES / "contact.jsonl", sidecar_path=FIXTURES / "contact.sidecar.jsonl")


def test_four_graders_write_required_schema_and_replay_without_network(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.runner import run_graders
    responses=[reply({"score":2,"reason":"Synthetic mock accuracy"}),reply(evaluations())]
    requests: list[dict[str, Any]]=[]
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return responses.pop(0)
    records=run_graders([trace()], LLMClient(settings, transport=transport), output=tmp_path / "scores.jsonl")
    assert len(records)==4
    assert [row.grader for row in records]==["trajectory_accuracy","trajectory_comprehensive","action_loop_detection","observation_information_gain"]
    assert all(row.status=="ok" for row in records)
    assert records[0].score==2 and records[1].score==1
    required={"trace_id","grader","score","reason","judge_model","thinking","openjudge_commit","timestamp","usage","repeat_id"}
    assert all(required <= set(row.to_dict()) for row in records)
    assert all(row.judge_model is None and row.thinking is None and row.usage["api_calls"]==0 for row in records[2:])
    assert len(requests)==2
    replay=run_graders([trace()], LLMClient(settings, offline=True), output=tmp_path / "offline.jsonl")
    assert [row.score for row in replay]==[row.score for row in records]
    assert all(row.usage["api_calls"]==0 for row in replay)
    assert all(row.usage["cached_calls"]==1 for row in replay[:2])
    assert len((tmp_path / "scores.jsonl").read_text().splitlines())==4


def test_upstream_accuracy_clamp_cannot_turn_invalid_score_into_a_pass(settings: Settings) -> None:
    from trajjudge.runner import run_graders
    responses=[reply({"score":99,"reason":"Invalid mock score"}),reply(evaluations())]
    records=run_graders([trace()], LLMClient(settings, transport=lambda request:responses.pop(0)))
    assert records[0].status=="error" and records[0].score is None


def test_empty_step_evaluation_is_not_a_numeric_zero_verdict(settings: Settings) -> None:
    from trajjudge.runner import run_graders
    responses=[reply({"score":2,"reason":"Mock"}),reply({"step_evaluations":[]})]
    records=run_graders([trace()], LLMClient(settings, transport=lambda request:responses.pop(0)))
    assert records[1].status=="error" and records[1].score is None


@pytest.mark.parametrize("failure", ["duplicate", "missing", "truncated"])
def test_incomplete_or_duplicate_steps_are_errors(settings: Settings, failure: str) -> None:
    from trajjudge.runner import run_graders
    body = evaluations()
    if failure == "duplicate":
        body["step_evaluations"][1]["step_index"] = 0
    elif failure == "missing":
        body["step_evaluations"].pop()
    response = reply(body)
    if failure == "truncated":
        response["choices"][0]["finish_reason"] = "length"
    responses = [reply({"score": 2, "reason": "Synthetic mock accuracy"}), response]
    records = run_graders([trace()], LLMClient(settings, transport=lambda request: responses.pop(0)))
    assert records[1].status == "error" and records[1].score is None


def test_semantic_mapping_gap_prevents_paid_scoring(settings: Settings) -> None:
    from trajjudge.runner import run_graders
    adapted=trace()
    adapted.metadata["unmapped_content"]=[{"value":{"type":"future_blob"}}]
    records=run_graders([adapted], LLMClient(settings, transport=lambda request:pytest.fail("must not call model")))
    assert len(records)==4
    assert all(row.status=="error" and row.score is None for row in records)


def test_transport_failure_checkpoints_error_and_stops_batch(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.runner import run_graders
    class Rejected(RuntimeError):
        status_code=400
    requests=[]
    def fail(request: dict[str, Any]) -> Any:
        requests.append(request)
        raise Rejected("synthetic rejection")
    records=run_graders([trace()], LLMClient(settings, transport=fail), output=tmp_path / "partial.jsonl")
    assert len(records)==1 and records[0].status=="error" and records[0].score is None
    assert records[0].metadata["fatal"] is True
    assert len(requests)==1
    assert json.loads((tmp_path / "partial.jsonl").read_text())["status"]=="error"


def test_validation_happens_before_upstream_callback(settings: Settings) -> None:
    from pydantic import ValidationError
    from openjudge.graders.agent.trajectory.trajectory_comprehensive import TrajectoryEvaluationOutput
    from trajjudge.openjudge_bridge import openjudge_model
    body=evaluations(1)
    body["step_evaluations"][0]["accuracy_score"]=99
    invoked=[]
    async def evaluate() -> None:
        async with openjudge_model(LLMClient(settings, transport=lambda request:reply(body))) as (model, bridge):
            await model.achat([{"role":"user","content":"Return JSON"}], structured_model=TrajectoryEvaluationOutput,
                              callback=lambda response:invoked.append(True))
    with pytest.raises(ValidationError):
        asyncio.run(evaluate())
    assert invoked==[]
