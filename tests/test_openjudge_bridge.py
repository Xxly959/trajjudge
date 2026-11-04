"""Exercise the real OpenJudge model/grader path with a mocked provider."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest

from trajjudge.config import Settings
from trajjudge.llm import LLMClient


def provider_reply(content: str = '{"score": 3, "reason": "Synthetic successful weather trace."}') -> dict[str, Any]:
    """Return a synthetic OpenAI response, not an experimental label."""
    return {"id": "mock-completion", "object": "chat.completion", "created": 1,
            "model": "judge-test", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": content, "reasoning_content": None}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}


def test_native_model_extra_body_and_cached_grader(settings: Settings) -> None:
    from openjudge.graders.agent import TrajectoryAccuracyGrader
    from trajjudge.openjudge_bridge import openjudge_model
    requests: list[dict[str, Any]] = []
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return provider_reply()
    client = LLMClient(settings, transport=transport)
    async def evaluate(shared: LLMClient) -> tuple[float, Any]:
        async with openjudge_model(shared, thinking=False) as (model, bridge):
            result = await TrajectoryAccuracyGrader(model=model).aevaluate(messages=[{"role": "user", "content": "Weather?"}])
            return result.score, bridge
    score, bridge = asyncio.run(evaluate(client))
    assert score == 3
    assert requests[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert bridge.observations[0]["thinking"] == {"type": "disabled"}
    assert bridge.results[0].raw_response["usage"]["total_tokens"] == 120
    replay_score, replay_bridge = asyncio.run(evaluate(LLMClient(replace(settings, api_key=""), offline=True)))
    assert replay_score == 3
    assert replay_bridge.results[0].cached
    assert len(requests) == 1


def test_response_format_is_part_of_cache_key(settings: Settings) -> None:
    requests: list[dict[str, Any]] = []
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return provider_reply()
    client = LLMClient(settings, transport=transport)
    client.complete([{"role": "user", "content": "JSON"}], response_format={"type": "json_object"})
    client.complete([{"role": "user", "content": "JSON"}])
    assert len(requests) == 2


def test_missing_score_is_grader_error(settings: Settings) -> None:
    from openjudge.graders.agent import TrajectoryAccuracyGrader
    from openjudge.graders.schema import GraderError
    from trajjudge.openjudge_bridge import openjudge_model
    async def evaluate() -> Any:
        shared = LLMClient(settings, transport=lambda request: provider_reply('{"reason": "Missing score"}'))
        async with openjudge_model(shared) as (model, bridge):
            return await TrajectoryAccuracyGrader(model=model).aevaluate(messages=[{"role": "user", "content": "Weather?"}])
    assert isinstance(asyncio.run(evaluate()), GraderError)


def test_bridge_rejects_unknown_parameters_before_transport(settings: Settings) -> None:
    import importlib
    from openai import DefaultAsyncHttpxClient
    from trajjudge.openjudge_bridge import SharedCompletionTransport
    http = importlib.import_module(DefaultAsyncHttpxClient.__mro__[1].__module__.split(".")[0])
    shared = LLMClient(settings, transport=lambda request: pytest.fail("must not call provider"))
    request = http.Request("POST", settings.base_url + "/chat/completions", json={
        "model": "judge-test", "messages": [], "thinking": {"type": "disabled"}, "unknown_field": 1,
    })
    with pytest.raises(ValueError, match="unsupported"):
        asyncio.run(SharedCompletionTransport(shared).handle_async_request(request))


def test_weather_fixture_matches_the_official_example() -> None:
    import ast
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root.parent / "OpenJudge/docs/built_in_graders/agent_graders.md").read_text()
    section = text.split("### TrajectoryAccuracyGrader", 1)[1].split("### TrajectoryComprehensiveGrader", 1)[0]
    code = section.split("```python", 1)[1].split("```", 1)[0]
    assignment = next(node for node in ast.walk(ast.parse(code)) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "messages" for target in node.targets))
    sample = json.loads((root / "samples/weather.json").read_text())
    assert sample["messages"] == ast.literal_eval(assignment.value)
