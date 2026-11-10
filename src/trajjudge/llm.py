"""Unified LLM client used by every script and grader in this project.

Responsibilities:

* talk to the DeepSeek OpenAI-compatible endpoint (``base_url`` from settings),
* retry 429/5xx/timeouts with exponential backoff and jitter,
* serve repeated requests from the disk cache without touching the network,
* append one usage record per call,
* echo ``reasoning_content`` back into assistant messages so that multi-turn
  tool-calling requests do not fail with HTTP 400 in thinking mode.

The API key is held in memory only; it is never logged or persisted here.
"""

from __future__ import annotations

import json
import math
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .cache import DiskCache, canonical_json, make_key
from .config import Settings
from .usage import UsageLog, UsageRecord, load_pricing, summarize, utc_now, budget_cost, load_reservations, request_reservation

Message = dict[str, Any]
Transport = Callable[[dict[str, Any]], Any]
SleepFn = Callable[[float], None]

RETRYABLE_STATUS = frozenset({408, 409, 429, *range(500, 600)})
CACHE_VERSION = 2


class LLMError(RuntimeError):
    """Raised when a request fails for good or the response is unusable."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call requested by the assistant."""

    call_id: str
    name: str
    arguments: str

    def to_openai(self) -> dict[str, Any]:
        """Return the OpenAI ``tool_calls`` entry for this call."""
        return {
            "id": self.call_id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }

    def parsed_arguments(self) -> dict[str, Any]:
        """Decode ``arguments`` as JSON, returning ``{}`` when it is not an object."""
        try:
            value = json.loads(self.arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True, slots=True)
class LLMResult:
    """A single assistant response plus bookkeeping."""

    text: str
    reasoning_content: str | None
    tool_calls: list[ToolCall]
    model: str
    thinking: bool
    prompt_tokens: int
    completion_tokens: int
    cached: bool = False
    latency_ms: float = 0.0
    tag: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def returned_reasoning(self) -> bool:
        """Whether the provider sent back non-empty reasoning content."""
        return bool(self.reasoning_content)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation (used by the cache)."""
        return {
            "text": self.text,
            "reasoning_content": self.reasoning_content,
            "tool_calls": [
                {"call_id": call.call_id, "name": call.name, "arguments": call.arguments}
                for call in self.tool_calls
            ],
            "model": self.model,
            "thinking": self.thinking,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": self.latency_ms,
            "tag": self.tag,
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, cached: bool) -> "LLMResult":
        """Rebuild a result from its cached representation."""
        calls = [
            ToolCall(
                call_id=str(item.get("call_id", "")),
                name=str(item.get("name", "")),
                arguments=str(item.get("arguments", "{}")),
            )
            for item in raw.get("tool_calls") or []
        ]
        return cls(
            text=str(raw.get("text", "")),
            reasoning_content=raw.get("reasoning_content"),
            tool_calls=calls,
            model=str(raw.get("model", "")),
            thinking=bool(raw.get("thinking", False)),
            prompt_tokens=int(raw.get("prompt_tokens", 0)),
            completion_tokens=int(raw.get("completion_tokens", 0)),
            cached=cached,
            latency_ms=0.0,
            tag=str(raw.get("tag", "")),
            raw_response=dict(raw.get("raw_response") or {}),
        )


def assistant_message(result: LLMResult) -> Message:
    """Build the assistant message to append to the conversation.

    DeepSeek rejects multi-turn thinking requests that carry ``tools`` when the
    previous assistant turn's ``reasoning_content`` is missing, so it is echoed
    verbatim whenever the provider returned it.
    """
    message: Message = {"role": "assistant", "content": result.text}
    if result.tool_calls:
        message["tool_calls"] = [call.to_openai() for call in result.tool_calls]
    if result.reasoning_content:
        message["reasoning_content"] = result.reasoning_content
    return message


def tool_result_message(call: ToolCall, content: str) -> Message:
    """Build the ``tool`` message answering ``call``."""
    return {"role": "tool", "tool_call_id": call.call_id, "content": content}


def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a dict or an SDK object."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _is_retryable(exc: BaseException) -> bool:
    status = _field(exc, "status_code") or _field(exc, "code")
    if isinstance(status, int):
        return status in RETRYABLE_STATUS
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    return any(
        marker in text or marker in name
        for marker in ("timeout", "timed out", "connection", "rate limit", "overloaded", "temporarily unavailable")
    )


class LLMClient:
    """Synchronous DeepSeek client with cache, retries and usage logging."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: Transport | None = None,
        client: Any | None = None,
        cache: DiskCache | None = None,
        usage_log: UsageLog | None = None,
        sleep: SleepFn = time.sleep,
        max_attempts: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        timeout: float = 180.0,
        offline: bool = False,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if max_attempts < 1 or timeout <= 0:
            raise ValueError("attempts and timeout must be positive")
        self.settings = settings
        self.cache = cache if cache is not None else DiskCache(settings.cache_dir)
        self.usage_log = usage_log if usage_log is not None else UsageLog(settings.usage_log)
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.timeout = timeout
        self.offline = offline
        self.last_models_cached = False
        self.jitter = jitter
        self._client = client
        self._transport: Transport | None = transport
        self._lock = threading.Lock()
        self._inflight = 0
        self._pending_count = 0
        self._reserved = 0.0

    # ---------------------------------------------------------------- client

    def _get_client(self) -> Any:
        if self.offline:
            raise LLMError("offline mode forbids SDK requests")
        if self._client is None:
            from openai import OpenAI  # imported lazily so tests stay offline

            self._client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._client

    def _default_transport(self, request: dict[str, Any]) -> Any:
        return self._get_client().chat.completions.create(**request)

    def list_models(self) -> list[str]:
        """Discover model IDs with cached metadata, retries and zero-token logs."""
        key = make_key({"endpoint": "models", "base_url": self.settings.base_url, "version": 1})
        cached = self.cache.get(key)
        self.last_models_cached = cached is not None
        if cached is not None:
            self._record_models(cached=True)
            return list(cached["models"])
        if self.offline:
            raise LLMError("offline mode: model-list cache miss")
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._get_client().models.list()
            except Exception as exc:
                self._record_models(status="error")
                if attempt >= self.max_attempts or not _is_retryable(exc):
                    raise LLMError(f"model discovery failed after {attempt} attempt(s)") from None
                delay = min(self.backoff_cap, self.backoff_base * 2 ** (attempt - 1))
                self.sleep(delay * (1 + 0.3 * self.jitter()))
                continue
            self._record_models()
            ids = sorted({str(_field(item, "id", "")) for item in _field(response, "data", []) or []} - {""})
            if not ids:
                raise LLMError("model discovery returned no model IDs")
            self.cache.put(key, {"models": ids, "timestamp": utc_now()})
            return ids
        raise LLMError("model discovery attempts exhausted")

    def _record_models(self, *, cached: bool = False, status: str = "success") -> None:
        self.usage_log.append(UsageRecord(
            timestamp=utc_now(), tag="models", model="model-discovery", thinking=False,
            prompt_tokens=0, completion_tokens=0, latency_ms=0, cached=cached,
            status=status, endpoint="models",
        ))

    # ------------------------------------------------------------- interface

    def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str | None = None,
        thinking: bool | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        tool_choice: str | Mapping[str, Any] | None = None,
        response_format: Mapping[str, Any] | None = None,
        tag: str = "",
        use_cache: bool = True,
        repeat_id: int | str | None = None,
    ) -> LLMResult:
        """Run one chat completion.

        Args:
            messages: OpenAI-style messages.
            model: Model id; defaults to the configured judge model.
            thinking: Whether to enable thinking; defaults to the configured
                switch for the judge role.
            tools: OpenAI tool schemas. Requires ``reasoning_content`` to be
                echoed back in subsequent assistant turns when thinking is on.
            temperature: Sampling temperature; omitted when ``None``.
            max_tokens: Completion cap; defaults to 1,024 when ``None``.
            reasoning_effort: Optional provider thinking effort, included in the cache key.
            tool_choice: Optional tool selection policy, included in the cache key.
            response_format: Optional JSON output format, included in the cache key.
            tag: Free-form label written into the usage log (e.g. ``smoke``).
            use_cache: Retained for compatibility; cache lookup and storage are always enabled.
            repeat_id: Index of an intentional repeated sample. Distinct values get
                distinct cache entries so repeats are real requests; ``None`` leaves
                the key unchanged (legacy entries stay valid).

        Returns:
            The parsed response, with ``cached=True`` on cache hits.

        Raises:
            LLMError: If every attempt failed or the response could not be parsed.
        """
        model_id = model or self.settings.judge_model
        if not model_id:
            raise LLMError("no model id configured; run the S2 probe and fill configs/deepseek.yaml")
        thinking_on = self.settings.judge_thinking if thinking is None else thinking

        request: dict[str, Any] = {"model": model_id, "messages": list(messages)}
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None and max_tokens <= 0:
            raise LLMError("max_tokens must be positive")
        request["max_tokens"] = max_tokens if max_tokens is not None else 1024
        if tools:
            request["tools"] = list(tools)
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        if reasoning_effort is not None:
            request["reasoning_effort"] = reasoning_effort
        if response_format is not None:
            request["response_format"] = dict(response_format)
        request["extra_body"] = {"thinking": {"type": "enabled" if thinking_on else "disabled"}}

        key_payload: dict[str, Any] = {
            "version": CACHE_VERSION,
            "base_url": self.settings.base_url,
            "model": model_id,
            "thinking": thinking_on,
            "messages": list(messages),
            "request": request,
            "tools": list(tools or []),
        }
        if repeat_id is not None:
            key_payload["repeat_id"] = repeat_id
        key = make_key(key_payload)

        cached = self.cache.get(key)
        if cached is not None:
            result = LLMResult.from_dict(cached, cached=True)
            self._record(result, tag=tag or result.tag)
            return result

        if self.offline:
            raise LLMError("offline mode: completion cache miss")
        with self._lock:
            reserve = self._check_budget(request)
            self._reserved += reserve
            self._inflight += 1
        started = time.monotonic()
        try:
            raw = self._call_with_retries(request, tag=tag, thinking=thinking_on)
        finally:
            with self._lock:
                self._reserved -= reserve
                self._inflight -= 1
        latency_ms = (time.monotonic() - started) * 1000
        result = self._parse(raw, model=model_id, thinking=thinking_on, latency_ms=latency_ms, tag=tag)

        self.cache.put(key, result.to_dict())
        return result

    # -------------------------------------------------------------- internals

    @property
    def _pending_path(self) -> Path:
        return self.usage_log.path.with_suffix(".pending")

    def _check_budget(self, request: dict[str, Any]) -> float:
        """Reserve a conservative per-byte input estimate and all output retries.

        Returns the reserved USD; in-flight reservations from other threads count
        toward the budget. Provider-side billing remains authoritative.
        Uncertain billing or interrupted accounting blocks subsequent requests.
        """
        if self._pending_path.exists() and self._inflight == 0:
            raise LLMError("unreconciled pending request; budget accounting is uncertain")
        prices = load_pricing(self.settings.pricing_file)
        price = prices.get(request["model"])
        if price is None:
            raise LLMError("verified pricing required before paid requests")
        accounted = budget_cost(self.usage_log.read(), prices, load_reservations(self.usage_log.path))
        if accounted is None:
            raise LLMError("budget accounting unknown; reconcile usage and pricing first")
        input_bound = len(canonical_json(request).encode("utf-8")) + 4096
        reserve = self.max_attempts * (
            input_bound * price.input_per_mtok
            + request["max_tokens"] * price.output_per_mtok
        ) / 1_000_000
        budget = self.settings.budget_usd
        if not math.isfinite(budget) or budget <= 0 or accounted + self._reserved + reserve > budget:
            raise LLMError("approved budget would be exceeded; request blocked")
        return reserve

    def _mark_pending(self) -> None:
        with self._lock:
            self._pending_count += 1
            self._pending_path.parent.mkdir(parents=True, exist_ok=True)
            self._pending_path.write_text("Accounting pending; reconcile before resuming.\n")

    def _clear_pending(self) -> None:
        """Remove the marker only when no attempt of this client is still unaccounted."""
        with self._lock:
            self._pending_count -= 1
            if self._pending_count == 0:
                self._pending_path.unlink(missing_ok=True)

    def _call_with_retries(self, request: dict[str, Any], *, tag: str, thinking: bool) -> Any:
        transport = self._transport or self._default_transport
        for attempt in range(1, self.max_attempts + 1):
            self._mark_pending()
            attempt_started = time.monotonic()
            try:
                raw = transport(request)
            except Exception as exc:
                status = _field(exc, "status_code")
                known_rejection = isinstance(status, int) and 400 <= status < 500 and status != 408
                price = load_pricing(self.settings.pricing_file).get(request["model"])
                evidence = {} if known_rejection or price is None else {"budget_reservation": request_reservation(request, price)}
                self.usage_log.append(UsageRecord(
                    timestamp=utc_now(), tag=tag, model=request["model"], thinking=thinking,
                    prompt_tokens=0, completion_tokens=0, latency_ms=(time.monotonic() - attempt_started) * 1000, cached=False,
                    status="rejected" if known_rejection else "unknown", usage_known=known_rejection,
                    raw_usage=evidence,
                ))
                self._clear_pending()
                if attempt >= self.max_attempts or not _is_retryable(exc):
                    raise LLMError(f"LLM request failed after {attempt} attempt(s); HTTP status {status if isinstance(status, int) else 'unknown'}") from None
                delay = min(self.backoff_cap, self.backoff_base * 2 ** (attempt - 1))
                self.sleep(delay * (1 + 0.3 * self.jitter()))
                continue
            usage = _field(raw, "usage")
            raw_usage = usage if isinstance(usage, dict) else (usage.model_dump() if hasattr(usage, "model_dump") else {})
            known = all(isinstance(raw_usage.get(k), int) and raw_usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens"))
            self.usage_log.append(UsageRecord(
                timestamp=utc_now(), tag=tag, model=request["model"], thinking=thinking,
                prompt_tokens=raw_usage.get("prompt_tokens", 0) if known else 0,
                completion_tokens=raw_usage.get("completion_tokens", 0) if known else 0,
                latency_ms=(time.monotonic() - attempt_started) * 1000, cached=False, usage_known=known, raw_usage=raw_usage,
            ))
            self._clear_pending()
            return raw
        raise LLMError("request attempts exhausted")

    def _parse(self, raw: Any, *, model: str, thinking: bool, latency_ms: float, tag: str) -> LLMResult:
        choices = _field(raw, "choices", []) or []
        if not choices:
            raise LLMError("response contained no choices")
        message = _field(choices[0], "message")
        if message is None:
            raise LLMError("response choice contained no message")

        calls = [
            ToolCall(
                call_id=str(_field(item, "id", "") or ""),
                name=str(_field(_field(item, "function", {}), "name", "") or ""),
                arguments=str(_field(_field(item, "function", {}), "arguments", "{}") or "{}"),
            )
            for item in (_field(message, "tool_calls", []) or [])
        ]
        usage = _field(raw, "usage", {}) or {}
        return LLMResult(
            text=str(_field(message, "content", "") or ""),
            reasoning_content=_field(message, "reasoning_content"),
            tool_calls=calls,
            model=model,
            thinking=thinking,
            prompt_tokens=int(_field(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(_field(usage, "completion_tokens", 0) or 0),
            cached=False,
            latency_ms=latency_ms,
            tag=tag,
            raw_response=dict(raw) if isinstance(raw, Mapping) else raw.model_dump(mode="json"),
        )

    def _record(self, result: LLMResult, *, tag: str) -> None:
        self.usage_log.append(
            UsageRecord(
                timestamp=utc_now(),
                tag=tag,
                model=result.model,
                thinking=result.thinking,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
                cached=result.cached,
            )
        )
