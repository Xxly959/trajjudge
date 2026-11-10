"""Lossless Claw-Eval JSONL to OpenAI message adaptation.

Every input event is retained verbatim in metadata, indexed by event position.
Mapped messages are a view; unsupported content is explicit, never discarded.
A matching S5 sidecar may supply the actual system prompt absent from the trace.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AdaptedTrace:
    """OpenAI messages and full source provenance for one executed trace."""

    trace_id: str
    task_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "task_id": self.task_id,
                "messages": self.messages, "metadata": self.metadata}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read object-valued JSONL without schema coercion or field loss."""
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"invalid trace JSON at line {line_number}") from None
        if not isinstance(event, dict):
            raise ValueError(f"trace line {line_number} must contain an object")
        events.append(event)
    return events


def validate_tool_links(messages: list[dict[str, Any]]) -> None:
    """Require unique calls and exactly one correctly linked result per call."""
    seen: set[str] = set()
    pending: set[str] = set()
    for message in messages:
        role = message["role"]
        if role == "tool":
            call_id = message.get("tool_call_id")
            if not call_id or call_id not in pending:
                raise ValueError("tool result has no matching pending call")
            pending.remove(call_id)
            continue
        if pending:
            raise ValueError("tool results are incomplete before the next conversation message")
        for call in message.get("tool_calls", []):
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id or call_id in seen:
                raise ValueError("tool call IDs must be nonempty and unique")
            seen.add(call_id)
            pending.add(call_id)
    if pending:
        raise ValueError("tool calls have no corresponding results")


def adapt_trace(path: Path, *, sidecar_path: Path | None = None) -> AdaptedTrace:
    """Map a trace without inventing system text, tool IDs or scoring labels."""
    path = Path(path)
    events = read_jsonl(path)
    starts = [event for event in events if event.get("type") == "trace_start"]
    if len(starts) != 1 or not starts[0].get("trace_id") or not starts[0].get("task_id"):
        raise ValueError("exactly one identified trace_start is required")
    trace_id, task_id = starts[0]["trace_id"], starts[0]["task_id"]
    if any(event.get("trace_id", trace_id) != trace_id for event in events):
        raise ValueError("mixed trace IDs are not supported")
    metadata: dict[str, Any] = {
        "adapter_version": 1, "source_path": str(path),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "events": {str(i): copy.deepcopy(event) for i, event in enumerate(events)},
        "event_message_map": {}, "unmapped_event_indices": [], "unmapped_content": [],
        "system_source": {"kind": "missing"}, "sidecar_events": [], "enrichments": [],
    }
    messages: list[dict[str, Any]] = []
    tool_names: dict[str, str] = {}

    def unknown(event_index: int, block_index: int, value: Any) -> None:
        metadata["unmapped_content"].append({"event_index": event_index, "block_index": block_index, "value": copy.deepcopy(value)})

    for index, event in enumerate(events):
        if event.get("type") != "message":
            metadata["unmapped_event_indices"].append(index)
            continue
        source = event.get("message")
        if not isinstance(source, dict):
            raise ValueError("message event must contain a message object")
        role = source.get("role")
        if role not in {"system", "user", "assistant"}:
            unknown(index, -1, source)
            continue
        content = source.get("content", [])
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            raise ValueError("message content must be a list or string")
        first = len(messages)
        if role == "assistant":
            texts: list[str] = []
            calls: list[dict[str, Any]] = []
            for block_index, block in enumerate(content):
                if not isinstance(block, dict):
                    unknown(index, block_index, block)
                elif block.get("type") == "text" and isinstance(block.get("text"), str):
                    texts.append(block["text"])
                elif block.get("type") == "tool_use":
                    if not isinstance(block.get("input", {}), dict) or not isinstance(block.get("id"), str) or not isinstance(block.get("name"), str):
                        raise ValueError("invalid tool use block")
                    call_id = block["id"]
                    if call_id in tool_names:
                        raise ValueError("duplicate tool call ID")
                    tool_names[call_id] = block["name"]
                    calls.append({"id": call_id, "type": "function", "function": {
                        "name": block["name"], "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)}})
                else:
                    unknown(index, block_index, block)
            mapped: dict[str, Any] = {"role": role, "content": "\n".join(texts) or (None if calls else "")}
            if calls:
                mapped["tool_calls"] = calls
            if source.get("reasoning_content") is not None:
                mapped["reasoning_content"] = source["reasoning_content"]
            messages.append(mapped)
        else:
            pending_text: list[str] = []
            def flush_text() -> None:
                if pending_text:
                    messages.append({"role": role, "content": "\n".join(pending_text)})
                    pending_text.clear()
            for block_index, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    pending_text.append(block["text"])
                elif isinstance(block, dict) and block.get("type") == "tool_result" and role == "user":
                    flush_text()
                    call_id = block.get("tool_use_id")
                    if call_id not in tool_names:
                        raise ValueError("tool result refers to an unknown call")
                    observations: list[str] = []
                    result_content = block.get("content", [])
                    if not isinstance(result_content, list):
                        raise ValueError("tool result content must be a list")
                    for child in result_content:
                        if isinstance(child, dict) and child.get("type") == "text" and isinstance(child.get("text"), str):
                            observations.append(child["text"])
                        else:
                            unknown(index, block_index, child)
                    messages.append({"role": "tool", "tool_call_id": call_id, "name": tool_names[call_id], "content": "\n".join(observations)})
                    metadata["enrichments"].append({"event_index": index, "field": "tool.name", "source": "matching assistant tool_use.name"})
                else:
                    flush_text()
                    unknown(index, block_index, block)
            flush_text()
            if not content:
                messages.append({"role": role, "content": ""})
        metadata["event_message_map"][str(index)] = list(range(first, len(messages)))

    if any(message["role"] == "system" for message in messages):
        metadata["system_source"] = {"kind": "trace"}
    if sidecar_path is not None:
        sidecar = read_jsonl(Path(sidecar_path))
        if any(event.get("trace_id") != trace_id for event in sidecar):
            raise ValueError("sidecar belongs to a different trace")
        metadata["sidecar_events"] = copy.deepcopy(sidecar)
        metadata["sidecar_path"] = str(sidecar_path)
        if metadata["system_source"]["kind"] == "missing":
            for row_index, row in enumerate(sidecar):
                if row.get("type") != "request" or row.get("role") != "agent":
                    continue
                systems = []
                for item in row.get("request", {}).get("messages", []):
                    if item.get("role") != "system":
                        break
                    systems.append(copy.deepcopy(item))
                if systems:
                    messages = systems + messages
                    for positions in metadata["event_message_map"].values():
                        positions[:] = [position + len(systems) for position in positions]
                    metadata["system_source"] = {"kind": "sidecar", "row_index": row_index, "count": len(systems)}
                    break
    history = [copy.deepcopy(event) for event in events if event.get("type") == "grading_result"]
    if any(event.get("task_id") != task_id for event in history):
        raise ValueError("grading result belongs to a different task")
    metadata["grading_history"] = history
    metadata["official_result"] = history[-1] if history else None
    metadata["has_trace_end"] = any(event.get("type") == "trace_end" for event in events)
    validate_tool_links(messages)
    return AdaptedTrace(trace_id=trace_id, task_id=task_id, messages=messages, metadata=metadata)
