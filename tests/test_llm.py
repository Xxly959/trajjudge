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


def test_use_cache_false_cannot_bypass_a_hit(settings: Settings) -> None:
    transport = Recorder([_response("a"), _response("b")])
    client = _client(settings, transport)

    client.complete([{"role": "user", "content": "hi"}])
    result = client.complete([{"role": "user", "content": "hi"}], use_cache=False)

    assert result.text == "a"
    assert len(transport.requests) == 1


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

    with pytest.raises(LLMError, match="HTTP status 400"):
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


def test_thinking_enabled_sends_explicit_extra_body(settings: Settings) -> None:
    transport = Recorder([_response("x", reasoning="because")])
    client = _client(settings, transport)

    result = client.complete([{"role": "user", "content": "hi"}], thinking=True)

    assert transport.requests[0]["extra_body"] == {"thinking": {"type": "enabled"}}
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


def test_usage_survives_cache_write_failure(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(settings, Recorder([_response()]))
    def fail(*args: Any) -> None:
        raise OSError("disk failure")
    monkeypatch.setattr(client.cache, "put", fail)
    with pytest.raises(OSError):
        client.complete([{"role": "user", "content": "hi"}])
    assert UsageLog(settings.usage_log).read()[0].prompt_tokens == 11


def test_malformed_response_still_records_usage(settings: Settings) -> None:
    client = _client(settings, Recorder([{"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 7}}]))
    with pytest.raises(LLMError):
        client.complete([{"role": "user", "content": "hi"}])
    assert UsageLog(settings.usage_log).read()[0].completion_tokens == 7


def test_unknown_price_blocks_transport(settings: Settings) -> None:
    settings.pricing_file.unlink()
    transport = Recorder([_response()])
    with pytest.raises(LLMError, match="pric"):
        _client(settings, transport).complete([{"role": "user", "content": "hi"}])
    assert not transport.requests


def test_budget_exhaustion_blocks_transport(settings: Settings) -> None:
    settings.pricing_file.write_text("models:\n  judge-test:\n    input_per_mtok: 1000000\n    output_per_mtok: 1000000\n")
    transport = Recorder([_response()])
    with pytest.raises(LLMError, match="budget"):
        _client(settings, transport).complete([{"role": "user", "content": "hi"}])
    assert not transport.requests


def test_failed_attempt_is_logged_and_error_redacted(settings: Settings) -> None:
    client = _client(settings, Recorder([RetryableError(400, settings.api_key)]))
    with pytest.raises(LLMError) as caught:
        client.complete([{"role": "user", "content": "hi"}])
    assert settings.api_key not in str(caught.value)
    assert caught.value.__suppress_context__
    assert len(UsageLog(settings.usage_log).read()) == 1


def test_sdk_retries_disabled(settings: Settings) -> None:
    client = LLMClient(settings)
    sdk = client._get_client()
    try:
        assert sdk.max_retries == 0
    finally:
        sdk.close()


def test_settings_repr_hides_key(settings: Settings) -> None:
    assert settings.api_key not in repr(settings)


def test_cache_hit_needs_no_price_or_network(settings: Settings) -> None:
    transport = Recorder([_response()])
    client = _client(settings, transport)
    client.complete([{"role": "user", "content": "hi"}])
    settings.pricing_file.unlink()
    assert client.complete([{"role": "user", "content": "hi"}]).cached
    assert len(transport.requests) == 1


def test_unknown_billing_blocks_next_call(settings: Settings) -> None:
    transport = Recorder([{"choices": [{"message": {"content": "ok"}}]}])
    client = _client(settings, transport)
    client.complete([{"role": "user", "content": "hi"}])
    with pytest.raises(LLMError, match="unknown"):
        client.complete([{"role": "user", "content": "different"}])
    assert len(transport.requests) == 1


def test_corrupt_usage_blocks_request(settings: Settings) -> None:
    settings.usage_log.parent.mkdir(parents=True)
    settings.usage_log.write_text("broken json")
    transport = Recorder([_response()])
    with pytest.raises(ValueError, match="corrupt"):
        _client(settings, transport).complete([{"role": "user", "content": "hi"}])
    assert not transport.requests


def test_log_write_failure_leaves_pending_guard(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(settings, Recorder([_response()]))
    def fail(*args: Any) -> None:
        raise OSError("disk failure")
    monkeypatch.setattr(client.usage_log, "append", fail)
    with pytest.raises(OSError):
        client.complete([{"role": "user", "content": "hi"}])
    other = _client(settings, Recorder([]))
    with pytest.raises(LLMError, match="pending"):
        other.complete([{"role": "user", "content": "hi"}])


def test_all_5xx_retry_and_attempts_logged(settings: Settings) -> None:
    transport = Recorder([RetryableError(501), _response()])
    assert _client(settings, transport).complete([{"role": "user", "content": "hi"}]).text == "ok"
    records = UsageLog(settings.usage_log).read()
    assert [record.status for record in records] == ["unknown", "success"]


def test_endpoint_participates_in_cache_identity(settings: Settings) -> None:
    from dataclasses import replace
    first = _client(settings, Recorder([_response("first")]))
    first.complete([{"role": "user", "content": "hi"}])
    second = _client(replace(settings, base_url="https://another.invalid"), Recorder([_response("second")]))
    assert second.complete([{"role": "user", "content": "hi"}]).text == "second"


def test_repeat_id_gives_independent_cache_entries(settings: Settings) -> None:
    transport = Recorder([_response("a"), _response("b")])
    client = _client(settings, transport)
    msgs = [{"role": "user", "content": "hi"}]
    first = client.complete(msgs, repeat_id=0)
    second = client.complete(msgs, repeat_id=1)
    again = client.complete(msgs, repeat_id=1)
    assert (first.text, second.text, again.text) == ("a", "b", "b")
    assert (first.cached, second.cached, again.cached) == (False, False, True)
    assert len(transport.requests) == 2


def test_no_repeat_id_keeps_legacy_cache_key(settings: Settings) -> None:
    transport = Recorder([_response("legacy"), _response("repeat0")])
    client = _client(settings, transport)
    msgs = [{"role": "user", "content": "hi"}]
    client.complete(msgs)
    assert client.complete(msgs).cached is True
    assert client.complete(msgs, repeat_id=0).text == "repeat0"
    assert len(transport.requests) == 2


def test_cumulative_usage_blocks_request(settings: Settings) -> None:
    from trajjudge.usage import UsageRecord, utc_now
    UsageLog(settings.usage_log).append(UsageRecord(
        timestamp=utc_now(), tag="previous-run", model="judge-test", thinking=False,
        prompt_tokens=3_000_000, completion_tokens=0, latency_ms=0, cached=False,
    ))
    transport = Recorder([_response()])
    with pytest.raises(LLMError, match="budget"):
        _client(settings, transport).complete([{"role": "user", "content": "hi"}])
    assert not transport.requests


def test_incomplete_usage_record_blocks_request(settings: Settings) -> None:
    settings.usage_log.parent.mkdir(parents=True)
    settings.usage_log.write_text("{}\n")
    transport = Recorder([_response()])
    with pytest.raises(ValueError, match="corrupt"):
        _client(settings, transport).complete([{"role": "user", "content": "hi"}])
    assert not transport.requests


def test_concurrent_calls_keep_ledger_and_pending_marker_consistent(settings: Settings) -> None:
    from concurrent.futures import ThreadPoolExecutor
    transport = Recorder([_response(str(i)) for i in range(24)])
    client = _client(settings, transport)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda i: client.complete([{"role": "user", "content": "hi"}], repeat_id=i), range(24)))
    assert len(transport.requests) == 24 and not any(r.cached for r in results)
    assert len(client.usage_log.read()) == 24
    assert not client._pending_path.exists()


def test_transient_unknown_is_reserved_but_remains_unknown(settings: Settings) -> None:
    from trajjudge.usage import budget_cost, load_pricing
    transport = Recorder([RetryableError(501), _response(), _response()])
    client = _client(settings, transport)
    client.complete([{"role": "user", "content": "hi"}])
    records = client.usage_log.read()
    assert records[0].usage_known is False and records[0].status == "unknown"
    assert "budget_reservation" in records[0].raw_usage
    assert budget_cost(records, load_pricing(settings.pricing_file)) is not None
    client.complete([{"role": "user", "content": "different"}])
    assert len(transport.requests) == 3
    from dataclasses import replace
    client.settings = replace(settings, budget_usd=.0000001)
    with pytest.raises(LLMError, match="budget"):
        client.complete([{"role": "user", "content": "another request"}])
    assert len(transport.requests) == 3
