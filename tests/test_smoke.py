"""Offline regression tests for the bounded S2 endpoint probe."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from trajjudge.config import Settings
from trajjudge.llm import LLMClient, LLMError
from trajjudge.usage import UsageLog


def response(text: str, *, reasoning: str | None = None, tool: str | None = None) -> dict[str, Any]:
    """Build a synthetic completion, never a real provider result."""
    calls = [] if tool is None else [{"id": "call-probe", "function": {"name": tool, "arguments": "{}"}}]
    return {"choices": [{"message": {"content": text, "reasoning_content": reasoning, "tool_calls": calls}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10}}


def test_models_are_cached_retried_and_logged(settings: Settings) -> None:
    attempts: list[int] = []
    def listing() -> Any:
        attempts.append(1)
        if len(attempts) == 1:
            error = RuntimeError("synthetic temporary failure")
            error.status_code = 503  # type: ignore[attr-defined]
            raise error
        return SimpleNamespace(data=[SimpleNamespace(id="judge-test")])
    client = LLMClient(settings, client=SimpleNamespace(models=SimpleNamespace(list=listing)), sleep=lambda _: None)
    assert client.list_models() == ["judge-test"]
    assert client.list_models() == ["judge-test"]
    assert len(attempts) == 2
    records = UsageLog(settings.usage_log).read()
    assert [record.endpoint for record in records] == ["models"] * 3
    assert records[-1].cached


def test_smoke_roundtrip_and_full_cache_replay(settings: Settings) -> None:
    from trajjudge.smoke import run_smoke
    requests: list[dict[str, Any]] = []
    items = [response("S2_READY"), response("5"), response("5", reasoning=" reason verbatim "),
             response("", reasoning="  tool reasoning verbatim\n", tool="get_probe_code"),
             response("S2_TOOL_OK_731", reasoning="done")]
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return items.pop(0)
    client = LLMClient(settings, transport=transport, max_attempts=3)
    results = run_smoke(client, "judge-test")
    assert len(results) == 5
    assert requests[-1]["messages"][-2]["reasoning_content"] == "  tool reasoning verbatim\n"
    assert requests[-1]["messages"][-1]["tool_call_id"] == "call-probe"
    assert requests[-1]["tool_choice"] == "none"
    assert requests[-1]["tools"] == requests[-2]["tools"]
    assert requests[2]["reasoning_effort"] == "low"
    assert requests[2]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert [row["returned_reasoning"] for row in results] == [False, False, True, True, True]
    replay = run_smoke(LLMClient(settings, offline=True), "judge-test")
    assert all(row["cached"] for row in replay)
    assert len(requests) == 5


def test_offline_miss_never_creates_sdk(settings: Settings) -> None:
    client = LLMClient(settings, offline=True)
    with pytest.raises(LLMError, match="offline"):
        client.complete([{"role": "user", "content": "hi"}])
    with pytest.raises(LLMError, match="offline"):
        client.list_models()
    assert client._client is None


def test_tool_probe_rejects_missing_reasoning(settings: Settings) -> None:
    from trajjudge.smoke import run_smoke
    items = [response("S2_READY"), response("5"), response("5", reasoning="ok"),
             response("", tool="get_probe_code")]
    client = LLMClient(settings, transport=lambda request: items.pop(0))
    with pytest.raises(LLMError, match="reasoning_content"):
        run_smoke(client, "judge-test")
    assert len(UsageLog(settings.usage_log).read()) == 4


def test_smoke_rejects_invalid_final_answer(settings: Settings) -> None:
    from trajjudge.smoke import run_smoke
    items = [response("S2_READY"), response("5"), response("5", reasoning="ok"),
             response("", reasoning="ok", tool="get_probe_code"), response("wrong", reasoning="ok")]
    client = LLMClient(settings, transport=lambda request: items.pop(0))
    with pytest.raises(LLMError, match="tool result"):
        run_smoke(client, "judge-test")
