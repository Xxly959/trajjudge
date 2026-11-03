"""Tests for the unified LLM client: caching, retries, usage, reasoning echo."""

from __future__ import annotations

from typing import Any

import pytest

from trajjudge.config import Settings
from trajjudge.llm import LLMClient, LLMError, assistant_message
from trajjudge.usage import UsageLog


class RetryableError(RuntimeError):
    """Stand-in for an SDK error carrying an HTTP status."""

    def __init__(self, status_code: int, message: str = "boom") -> None:
        super().__init__(message)
        self.status_code = status_code


def _response(content: str = "ok", reasoning: str | None = None, tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "content": content,
                    "reasoning_content": reasoning,
                    "tool_calls": tool_calls or [],
                }
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }


class Recorder:
    """Transport double that counts calls and replays queued items."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: dict[str, Any]) -> Any:
        self.requests.append(request)
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _client(settings: Settings, transport: Recorder, sleeps: list[float] | None = None) -> LLMClient:
    return LLMClient(
        settings,
        transport=transport,
        sleep=(sleeps.append if sleeps is not None else (lambda _: None)),
        backoff_base=1.0,
        jitter=lambda: 0.0,
    )


def test_second_identical_call_is_served_from_cache(settings: Settings) -> None:
    transport = Recorder([_response("hello")])
    client = _client(settings, transport)

    first = client.complete([{"role": "user", "content": "hi"}], tag="t")
    second = client.complete([{"role": "user", "content": "hi"}], tag="t")

    assert first.cached is False
    assert second.cached is True
    assert second.text == "hello"
    assert len(transport.requests) == 1


def test_cache_hit_still_logs_usage(settings: Settings) -> None:
    transport = Recorder([_response("hello")])
    client = _client(settings, transport)

    client.complete([{"role": "user", "content": "hi"}])
    client.complete([{"role": "user", "content": "hi"}])

    records = UsageLog(settings.usage_log).read()
    assert [record.cached for record in records] == [False, True]
    assert records[1].prompt_tokens == 11


def test_use_cache_false_forces_a_request(settings: Settings) -> None:
    transport = Recorder([_response("a"), _response("b")])
    client = _client(settings, transport)

    client.complete([{"role": "user", "content": "hi"}])
    result = client.complete([{"role": "user", "content": "hi"}], use_cache=False)

    assert result.text == "b"
    assert len(transport.requests) == 2


def test_retries_429_then_succeeds(settings: Settings) -> None:
    sleeps: list[float] = []
    transport = Recorder([RetryableError(429), RetryableError(503), _response("finally")])
    client = _client(settings, transport, sleeps)

    result = client.complete([{"role": "user", "content": "hi"}])

    assert result.text == "finally"
    assert len(transport.requests) == 3
    assert sleeps == [1.0, 2.0]


def test_non_retryable_error_fails_fast(settings: Settings) -> None:
    transport = Recorder([RetryableError(400, "bad request")])
    client = _client(settings, transport)

    with pytest.raises(LLMError, match="bad request"):
        client.complete([{"role": "user", "content": "hi"}])

    assert len(transport.requests) == 1


def test_retries_exhausted_raises(settings: Settings) -> None:
    transport = Recorder([RetryableError(500) for _ in range(3)])
    client = LLMClient(settings, transport=transport, max_attempts=3, sleep=lambda _: None)

    with pytest.raises(LLMError, match="3 attempt"):
        client.complete([{"role": "user", "content": "hi"}])


def test_thinking_disabled_sends_extra_body(settings: Settings) -> None:
    transport = Recorder([_response("x")])
    client = _client(settings, transport)

    client.complete([{"role": "user", "content": "hi"}], thinking=False)

    assert transport.requests[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_thinking_enabled_omits_extra_body(settings: Settings) -> None:
    transport = Recorder([_response("x", reasoning="because")])
    client = _client(settings, transport)

    result = client.complete([{"role": "user", "content": "hi"}], thinking=True)

    assert "extra_body" not in transport.requests[0]
    assert result.returned_reasoning is True


def test_assistant_message_echoes_reasoning_and_tool_calls(settings: Settings) -> None:
    tool_calls = [
        {
            "id": "call_1",
            "function": {"name": "get_weather", "arguments": '{"city": "Beijing"}'},
        }
    ]
    transport = Recorder([_response("", reasoning="need the weather", tool_calls=tool_calls)])
    client = _client(settings, transport)

    result = client.complete([{"role": "user", "content": "weather?"}], thinking=True)
    message = assistant_message(result)

    assert message["role"] == "assistant"
    assert message["reasoning_content"] == "need the weather"
    assert message["tool_calls"][0]["function"]["name"] == "get_weather"
    assert result.tool_calls[0].parsed_arguments() == {"city": "Beijing"}


def test_missing_choices_raises(settings: Settings) -> None:
    transport = Recorder([{"choices": []}])
    client = _client(settings, transport)

    with pytest.raises(LLMError, match="no choices"):
        client.complete([{"role": "user", "content": "hi"}])
