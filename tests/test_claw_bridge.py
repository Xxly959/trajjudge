"""Offline checks for native Claw provider/judge calls and worker bindings."""

from __future__ import annotations

import json
import multiprocessing
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from trajjudge.config import Settings
from trajjudge.llm import LLMClient, LLMError
from trajjudge.usage import UsageLog

SOURCE = Path(__file__).resolve().parents[2] / "claw-eval" / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))
sys.dont_write_bytecode = True


def reply(content: str = "OK") -> dict[str, Any]:
    """Return a synthetic provider response for offline integration tests."""
    return {"id": "mock", "object": "chat.completion", "created": 1, "model": "judge-test",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}


def spawn_probe(settings: Settings, output: str) -> dict[str, Any]:
    """Run the same binding entry in an independently spawned interpreter."""
    from trajjudge.claw_bridge import ClawSession, native_bindings
    from claw_eval.models.message import Message
    requests: list[dict[str, Any]] = []
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return reply()
    shared = LLMClient(replace(settings, agent_model=settings.judge_model), transport=transport)
    session = ClawSession(shared, "T010_contact_lookup", Path(output), max_turns=15)
    with native_bindings(session):
        from claw_eval.runner.providers.openai_compat import OpenAICompatProvider
        provider = OpenAICompatProvider(model_id=settings.judge_model, api_key=settings.api_key,
                    base_url=settings.base_url, extra_body={"thinking": {"type": "disabled"}, "max_tokens": 1024})
        message, usage = provider.chat([Message(role="system", content="Actual system"), Message(role="user", content="Hi")])
    return {"text": message.text, "usage": usage.input_tokens, "requests": len(requests), "thinking": requests[0]["extra_body"]}


def test_provider_binding_works_after_spawn(settings: Settings, tmp_path: Path) -> None:
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        result = pool.apply(spawn_probe, (settings, str(tmp_path / "sidecar")))
    assert result == {"text": "OK", "usage": 20, "requests": 1, "thinking": {"thinking": {"type": "disabled"}}}
    assert settings.api_key not in (tmp_path / "sidecar" / "requests.jsonl").read_text()


def test_native_judge_and_direct_client_use_shared_ledger(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.claw_bridge import ClawSession, native_bindings
    requests: list[dict[str, Any]] = []
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return reply('{"score": 0.9, "reasoning": "Synthetic judgment"}')
    shared = LLMClient(settings, transport=transport)
    with native_bindings(ClawSession(shared, "T010_contact_lookup", tmp_path / "one", max_turns=15)):
        from claw_eval.graders.llm_judge import LLMJudge
        judge = LLMJudge(model_id=settings.judge_model, api_key=settings.api_key, base_url=settings.base_url)
        assert judge.evaluate("task", "conversation", "actions", "rubric").score == 0.9
    with native_bindings(ClawSession(shared, "T002_email_triage", tmp_path / "two", max_turns=20)):
        from claw_eval.graders.llm_judge import LLMJudge
        judge = LLMJudge(model_id=settings.judge_model, api_key=settings.api_key, base_url=settings.base_url)
        assert judge.client.chat.completions.create(model=settings.judge_model, messages=[{"role":"user","content":"classify"}], max_tokens=8192).choices[0].message.content
    assert len(requests) == 2
    assert all(request["extra_body"] == {"thinking": {"type": "enabled"}} for request in requests)
    assert len(UsageLog(settings.usage_log).read()) == 2


def test_budget_failure_escapes_native_retry_loop(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from trajjudge.claw_bridge import ClawSession, S5Stop, native_bindings
    shared = LLMClient(settings)
    attempts: list[int] = []
    def fail(*args: Any, **kwargs: Any) -> Any:
        attempts.append(1)
        raise LLMError("budget blocked")
    monkeypatch.setattr(shared, "complete", fail)
    with native_bindings(ClawSession(shared, "T010_contact_lookup", tmp_path, max_turns=15)):
        from claw_eval.graders.llm_judge import LLMJudge
        with pytest.raises(S5Stop, match="budget blocked"):
            LLMJudge(model_id=settings.judge_model, api_key=settings.api_key, base_url=settings.base_url).evaluate("t", "c", "a", "r")
    assert len(attempts) == 1


def test_quota_and_unknown_parameters_never_send_more_requests(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.claw_bridge import ClawSession, S5Stop
    requests: list[dict[str, Any]] = []
    def transport(request: dict[str, Any]) -> Any:
        requests.append(request)
        return reply()
    session = ClawSession(LLMClient(settings, transport=transport), "T002_email_triage", tmp_path, max_turns=20)
    params = {"model":settings.judge_model,"messages":[{"role":"user","content":"x"}],"max_tokens":8192}
    session.create("judge", **params)
    with pytest.raises(S5Stop, match="quota"):
        session.create("judge", **params)
    with pytest.raises(S5Stop, match="unsupported"):
        session.create("agent", unknown_field=1, **params)
    assert len(requests) == 1


def test_request_and_system_sidecar_are_bound_to_trace(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.claw_bridge import ClawSession, native_bindings
    shared = LLMClient(replace(settings, agent_model=settings.judge_model), transport=lambda request: reply())
    session = ClawSession(shared, "T010_contact_lookup", tmp_path, max_turns=15)
    with native_bindings(session):
        from claw_eval.runner.loop import TraceWriter
        from claw_eval.models.trace import TraceStart
        with TraceWriter(tmp_path / "trace.jsonl") as writer:
            writer.write_event(TraceStart(trace_id="real-trace-id", task_id=session.task_id, model=settings.judge_model))
        session.create("agent", model=settings.judge_model, messages=[{"role":"system","content":"Exact system"}],
                       extra_body={"thinking":{"type":"disabled"},"max_tokens":1024})
    record = json.loads((tmp_path / "requests.jsonl").read_text().splitlines()[0])
    assert record["trace_id"] == "real-trace-id"
    assert record["request"]["messages"][0]["content"] == "Exact system"


def bounded_spawn_probe(settings: Settings, output: str) -> dict[str, Any]:
    import os
    import trajjudge.claw_bridge as bridge
    import claw_eval.cli as cli
    from claw_eval.models.message import Message
    original_client = LLMClient
    bridge.load_settings = lambda: replace(settings, agent_model=settings.judge_model)
    bridge.LLMClient = lambda resolved, **kwargs: original_client(resolved, transport=lambda request: reply())
    os.environ["TRAJJUDGE_S5_CEILING"] = "3"
    def native_callback(**kwargs: Any) -> dict[str, Any]:
        from claw_eval.runner.providers.openai_compat import OpenAICompatProvider
        provider = OpenAICompatProvider(model_id=settings.judge_model, api_key=settings.api_key, base_url=settings.base_url,
                                       extra_body={"thinking":{"type":"disabled"},"max_tokens":1024})
        result, usage = provider.chat([Message(role="user", content="Hi")])
        return {"answer": result.text}
    cli._run_single_task = native_callback
    try:
        return bridge.bounded_worker(task_dir=str(SOURCE.parents[0] / "tasks/T010_contact_lookup"), trials=1, trace_dir=output)
    except BaseException as exc:
        return {"error": type(exc).__name__}


def test_actual_bounded_worker_bootstrap_in_spawn(settings: Settings, tmp_path: Path) -> None:
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        result = pool.apply_async(bounded_spawn_probe, (settings, str(tmp_path))).get(timeout=20)
    assert result == {"answer": "OK"}


def test_missing_configuration_never_falls_back_to_native_defaults(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.claw_pilot import validate_configuration
    from trajjudge.claw_bridge import S5Stop
    with pytest.raises(S5Stop, match="config"):
        validate_configuration(tmp_path / "missing.yaml", settings)


def test_profile_allows_thinking_agent_and_prefixes_tags(settings: Settings, tmp_path: Path) -> None:
    from trajjudge.claw_bridge import ClawSession, S5Stop
    seen: list[dict[str, Any]] = []
    def transport(request: dict[str, Any]) -> Any:
        seen.append(request)
        return reply()
    client = LLMClient(replace(settings, agent_model=settings.judge_model), transport=transport)
    session = ClawSession(client, "T", tmp_path, max_turns=2, agent_thinking=True, agent_cap=4096, tag_prefix="p2/x")
    session.create("agent", model=settings.judge_model, messages=[{"role": "user", "content": "hi"}],
                   extra_body={"thinking": {"type": "enabled"}, "max_tokens": 4096})
    assert seen[0]["extra_body"] == {"thinking": {"type": "enabled"}} and seen[0]["max_tokens"] == 4096
    assert client.usage_log.read()[-1].tag == "p2/x/T/agent"
    with pytest.raises(S5Stop):
        session.create("agent", model=settings.judge_model, messages=[{"role": "user", "content": "hi"}],
                       extra_body={"thinking": {"type": "disabled"}})
