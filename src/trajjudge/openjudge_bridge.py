"""Keep the native OpenJudge model path behind the shared cached transport.

The SDK HTTP transport is local: it delegates to LLMClient instead of opening a
second network path. Only serial non-streaming chat completions are supported.
DeepSeek JSON-object output is validated against the original grader schema.
"""

from __future__ import annotations

import importlib
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from openai import DefaultAsyncHttpxClient
from openjudge.models import OpenAIChatModel

from .llm import LLMClient, LLMResult


class SharedCompletionTransport:
    """Route SDK JSON bodies through the shared client without logging headers."""

    def __init__(self, client: LLMClient, tag: str = "s3/weather") -> None:
        self.client = client
        self.tag = tag
        self.results: list[LLMResult] = []
        self.observations: list[dict[str, Any]] = []

    async def __aenter__(self) -> SharedCompletionTransport:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """The shared client owns its network lifetime; this transport owns none."""

    async def handle_async_request(self, request: Any) -> Any:
        """Reject unsupported fields rather than silently changing a judge call."""
        if request.method != "POST" or not request.url.path.endswith("/chat/completions"):
            raise ValueError("unsupported OpenJudge endpoint")
        payload = json.loads(await request.aread())
        allowed = {"model", "messages", "stream", "thinking", "temperature", "max_tokens",
                   "reasoning_effort", "tools", "tool_choice", "response_format"}
        if set(payload) - allowed or payload.get("stream", False):
            raise ValueError("unsupported OpenJudge request parameters or streaming")
        thinking = payload.get("thinking")
        if thinking not in ({"type": "enabled"}, {"type": "disabled"}):
            raise ValueError("an explicit thinking toggle is required")
        self.observations.append({
            "thinking": thinking, "response_format": payload.get("response_format"),
            "request_fields": sorted(payload),
        })
        parameters = {key: value for key, value in payload.items() if key not in {"thinking", "stream", "messages"}}
        result = self.client.complete(payload["messages"], thinking=thinking["type"] == "enabled", tag=self.tag, **parameters)
        self.results.append(result)
        if not result.raw_response:
            raise ValueError("cache lacks a complete provider response for native SDK replay")
        # OpenAI SDK versions may use httpx or httpx2. Reuse the version that
        # created this request instead of adding a competing HTTP dependency.
        http = importlib.import_module(type(request).__module__.split(".")[0])
        return http.Response(200, json=result.raw_response, request=request)


class DeepSeekOpenJudgeModel(OpenAIChatModel):
    """Use DeepSeek JSON objects while retaining native prompts and parsing."""

    async def achat(self, messages: list[Any], tools: list[dict[str, Any]] | None = None,
                    tool_choice: str | None = None, structured_model: Any = None,
                    callback: Any = None, **kwargs: Any) -> Any:
        response = await super().achat(
            messages=messages, tools=tools, tool_choice=tool_choice,
            structured_model={"type": "json_object"} if structured_model is not None else None,
            callback=callback, **kwargs,
        )
        if isinstance(structured_model, type) and hasattr(structured_model, "model_validate"):
            structured_model.model_validate(response.parsed)
        return response


@asynccontextmanager
async def openjudge_model(client: LLMClient, *, thinking: bool = False,
                          max_tokens: int = 768, tag: str = "s3/weather") -> AsyncIterator[tuple[DeepSeekOpenJudgeModel, SharedCompletionTransport]]:
    """Provide the native upstream chat path with local JSON adaptation and transport."""
    bridge = SharedCompletionTransport(client, tag=tag)
    http_client = DefaultAsyncHttpxClient(transport=bridge)
    model = DeepSeekOpenJudgeModel(
        model=client.settings.judge_model,
        api_key=client.settings.api_key or "offline-placeholder",
        base_url=client.settings.base_url, stream=False, max_retries=0, timeout=60,
        client_args={"http_client": http_client}, max_tokens=max_tokens,
        extra_body={"thinking": {"type": "enabled" if thinking else "disabled"}},
    )
    try:
        yield model, bridge
    finally:
        await model.client.close()
