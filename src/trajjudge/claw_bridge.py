"""Project-local, serial Claw-Eval bindings for the two approved S5 tasks.

Native message conversion, response parsing, execution and graders are retained.
Network calls use LLMClient. S5Stop deliberately bypasses upstream retry catches;
worker and container context managers still unwind and clean their resources.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from openai.types.chat import ChatCompletion

from .cache import canonical_json, make_key
from .config import load_settings
from .llm import LLMClient, LLMError
from .usage import load_pricing, summarize, utc_now

TASKS = {"T010_contact_lookup": 15, "T002_email_triage": 20}
INPUT_ESTIMATE_CAP = 48_000


class S5Stop(BaseException):
    """Abort the pilot without being swallowed by upstream Exception retries."""


class ClawSession:
    """One task's request quotas, exact request snapshots and shared client."""

    def __init__(self, client: LLMClient, task_id: str, output: Path, *, max_turns: int,
                 agent_thinking: bool = False, agent_cap: int = 1024, judge_quota: int = 1,
                 input_cap: int = INPUT_ESTIMATE_CAP, tag_prefix: str = "s5") -> None:
        self.tag_prefix = tag_prefix
        self.agent_thinking, self.agent_cap = agent_thinking, agent_cap
        self.judge_quota, self.input_cap = judge_quota, input_cap
        self.client = client
        self.task_id = task_id
        self.output = Path(output)
        self.max_turns = max_turns
        self.counts = {"agent": 0, "judge": 0}
        self.trace_id: str | None = None

    def snapshot(self, data: dict[str, Any]) -> None:
        """Write only request bodies/results metadata, never SDK auth headers."""
        self.output.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": utc_now(), "task_id": self.task_id, "trace_id": self.trace_id, **data}
        with (self.output / "requests.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def validate_identity(self, role: str, model: str, api_key: str | None, base_url: str | None) -> None:
        """Stop if native configuration drifts from the approved shared endpoint."""
        expected = self.client.settings.agent_model if role == "agent" else self.client.settings.judge_model
        if model != expected or api_key != self.client.settings.api_key or (base_url or "").rstrip("/") != self.client.settings.base_url.rstrip("/"):
            raise S5Stop("model endpoint or credentials did not match the shared client")

    def sdk(self, role: str) -> Any:
        """Expose the native SDK call surface used by task graders."""
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: self.create(role, **kwargs))), close=lambda: None)

    def create(self, role: str, **kwargs: Any) -> ChatCompletion:
        """Apply limits before all provider and direct judge.client requests."""
        allowed = {"model", "messages", "tools", "tool_choice", "temperature", "max_tokens", "reasoning_effort", "response_format", "extra_body", "stream"}
        if role not in self.counts or set(kwargs) - allowed or kwargs.get("stream", False):
            raise S5Stop("unsupported role, request parameter or streaming")
        params = {key: value for key, value in kwargs.items() if key not in {"extra_body", "stream"}}
        extra = dict(kwargs.get("extra_body") or {})
        if set(extra) - {"thinking", "max_tokens"}:
            raise S5Stop("unsupported extra_body parameter")
        thinking_body = extra.pop("thinking", {"type": "enabled"} if role == "judge" else None)
        if thinking_body not in ({"type": "enabled"}, {"type": "disabled"}):
            raise S5Stop("explicit thinking mode is required for the agent")
        thinking = thinking_body["type"] == "enabled"
        if role == "agent" and thinking != self.agent_thinking:
            raise S5Stop("agent thinking mode differs from the approved profile")
        for key, value in extra.items():
            if key in params and params[key] != value:
                raise S5Stop("conflicting request parameters")
            params[key] = value
        cap = self.agent_cap if role == "agent" else 8192
        params.setdefault("max_tokens", cap)
        if type(params["max_tokens"]) is not int or not 0 < params["max_tokens"] <= cap:
            raise S5Stop("completion token limit exceeds the approved cap")
        expected = self.client.settings.agent_model if role == "agent" else self.client.settings.judge_model
        if params.get("model") != expected:
            raise S5Stop("unapproved model")
        if self.counts[role] >= (self.max_turns if role == "agent" else self.judge_quota):
            raise S5Stop(f"{role} request quota exhausted")
        request = {**params, "extra_body": {"thinking": thinking_body}}
        estimate = len(canonical_json(request).encode("utf-8")) + 4096
        if estimate > self.input_cap:
            raise S5Stop("input estimate exceeds the pilot envelope; no content was truncated")
        self.counts[role] += 1
        request_hash = make_key(request)
        self.snapshot({"type": "request", "role": role, "request_hash": request_hash, "request": request, "input_estimate": estimate})
        try:
            messages = params.pop("messages")
            result = self.client.complete(messages, thinking=thinking, tag=f"{self.tag_prefix}/{self.task_id}/{role}", **params)
        except LLMError as exc:
            self.snapshot({"type": "stopped", "role": role, "category": "LLMError"})
            raise S5Stop(str(exc)) from None
        except Exception as exc:
            self.snapshot({"type": "stopped", "role": role, "category": type(exc).__name__})
            raise S5Stop(f"shared request failed ({type(exc).__name__})") from None
        self.snapshot({"type": "completion", "role": role, "request_hash": request_hash,
                       "cached": result.cached, "thinking": result.thinking,
                       "returned_reasoning": result.returned_reasoning,
                       "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens}})
        summary = summarize(self.client.usage_log.read(), load_pricing(self.client.settings.pricing_file))
        if summary.cost_usd is None or summary.cost_usd > self.client.settings.budget_usd:
            raise S5Stop("unknown or exceeded cumulative budget; pilot stopped")
        try:
            response = ChatCompletion.model_validate(result.raw_response)
        except Exception:
            raise S5Stop("provider response could not be validated") from None
        if not response.choices or response.choices[0].finish_reason not in {"stop", "tool_calls"}:
            raise S5Stop("provider response was incomplete or filtered")
        return response


@contextmanager
def native_bindings(session: ClawSession) -> Iterator[None]:
    """Install scoped bindings inside each worker, including trace provenance."""
    from claw_eval.runner import loop
    from claw_eval.runner.providers import openai_compat as provider_module
    from claw_eval.graders import llm_judge as judge_module
    from claw_eval.trace import writer as writer_module
    Provider, Judge, Writer = provider_module.OpenAICompatProvider, judge_module.LLMJudge, writer_module.TraceWriter
    old_loop_writer = loop.TraceWriter

    class SharedProvider(Provider):
        def __init__(self, **kwargs: Any) -> None:
            session.validate_identity("agent", kwargs.get("model_id", ""), kwargs.get("api_key"), kwargs.get("base_url"))
            super().__init__(**kwargs)
            self.client.close()
            self.client = session.sdk("agent")

        def chat(self, messages: list[Any], tools: list[Any] | None = None) -> tuple[Any, Any]:
            converted: list[dict[str, Any]] = []
            for message in messages:
                value = provider_module._message_to_openai(message, self._reasoning_field)
                converted.extend(value if isinstance(value, list) else [value])
            params: dict[str, Any] = {"model": self.model_id, "messages": converted, "extra_body": self.extra_body}
            if self.temperature is not None:
                params["temperature"] = self.temperature
            if self.reasoning_effort:
                params["reasoning_effort"] = self.reasoning_effort
            if tools:
                params["tools"] = [provider_module._tool_spec_to_openai(tool) for tool in tools]
            return self._parse_response(self.client.chat.completions.create(**params))

    class SharedJudge(Judge):
        def __init__(self, **kwargs: Any) -> None:
            session.validate_identity("judge", kwargs.get("model_id", ""), kwargs.get("api_key"), kwargs.get("base_url"))
            super().__init__(**kwargs)
            self.client.close()
            self.client = session.sdk("judge")

    class CapturingWriter(Writer):
        def write_event(self, event: Any) -> None:
            if event.type == "trace_start":
                session.trace_id = event.trace_id
            super().write_event(event)

    provider_module.OpenAICompatProvider = SharedProvider
    judge_module.LLMJudge = SharedJudge
    writer_module.TraceWriter = CapturingWriter
    loop.TraceWriter = CapturingWriter
    try:
        yield
    finally:
        provider_module.OpenAICompatProvider, judge_module.LLMJudge, writer_module.TraceWriter = Provider, Judge, Writer
        loop.TraceWriter = old_loop_writer


def load_profile() -> dict[str, Any]:
    """Return the run profile from ``TRAJJUDGE_CLAW_PROFILE`` (JSON path) or the S5 default.

    A profile holds ``tasks`` (id -> max_turns whitelist), ``agent_thinking``,
    ``agent_cap``, ``judge_quota``, ``input_cap`` and ``tag_prefix``; it is inherited by spawned workers.
    """
    path = os.environ.get("TRAJJUDGE_CLAW_PROFILE")
    default = {"tasks": TASKS, "agent_thinking": False, "agent_cap": 1024, "judge_quota": 1, "input_cap": INPUT_ESTIMATE_CAP, "tag_prefix": "s5"}
    return {**default, **json.loads(Path(path).read_text())} if path else default


def bounded_worker(**kwargs: Any) -> dict[str, Any]:
    """Spawn-safe native batch worker; bindings are created in the child process."""
    from claw_eval import cli
    from claw_eval.models.task import TaskDefinition
    profile = load_profile()
    tasks = profile["tasks"]
    task_id = Path(kwargs["task_dir"]).name
    if task_id not in tasks or kwargs["trials"] != 1:
        raise S5Stop("worker task/trial is outside the approved whitelist")
    task = TaskDefinition.from_yaml(Path(kwargs["task_dir"]) / "task.yaml")
    if task.user_agent.enabled or task.environment.max_turns != tasks[task_id] or task.environment.enable_compact or task.environment.enable_todo:
        raise S5Stop("task runtime settings changed from reconnaissance")
    settings = replace(load_settings(), budget_usd=float(os.environ["TRAJJUDGE_S5_CEILING"]))
    client = LLMClient(settings, max_attempts=3, timeout=60)
    session = ClawSession(client, task_id, Path(kwargs["trace_dir"]) / "s5_sidecar", max_turns=tasks[task_id],
                          agent_thinking=profile["agent_thinking"], agent_cap=profile["agent_cap"],
                          judge_quota=profile["judge_quota"], input_cap=profile["input_cap"],
                          tag_prefix=profile["tag_prefix"])
    # The child imports native CLI afresh under macOS spawn. Refuse accidental
    # recursion if this entry is ever invoked in a patched parent interpreter.
    native_worker = cli._run_single_task
    if native_worker is bounded_worker:
        raise S5Stop("worker did not start in an isolated spawn interpreter")
    try:
        with native_bindings(session):
            return native_worker(**kwargs)
    except S5Stop as exc:
        session.snapshot({"type": "stopped", "category": "S5Stop", "reason": str(exc)})
        raise
