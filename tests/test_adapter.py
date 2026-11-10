"""Structural S5 goldens with synthetic content."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from trajjudge.adapter import adapt_trace

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"


@pytest.mark.parametrize("name,tool_count", [("contact", 2), ("email", 8)])
def test_structural_golden_and_lossless_metadata(name: str, tool_count: int) -> None:
    path = FIXTURES / f"{name}.jsonl"
    trace = adapt_trace(path, sidecar_path=FIXTURES / f"{name}.sidecar.jsonl")
    assert trace.messages == json.loads((FIXTURES / f"{name}.messages.json").read_text())
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert trace.metadata["events"] == {str(i): event for i, event in enumerate(events)}
    assert trace.metadata["system_source"]["kind"] == "sidecar"
    assert trace.metadata["official_result"]["task_score"] == (0.804 if name == "contact" else 0.85)
    assert sum(message["role"] == "tool" for message in trace.messages) == tool_count


def test_missing_system_is_recorded_not_invented() -> None:
    trace = adapt_trace(FIXTURES / "contact.jsonl")
    assert trace.messages[0]["role"] == "user"
    assert trace.metadata["system_source"]["kind"] == "missing"


def test_unknown_content_and_event_remain_in_metadata(tmp_path: Path) -> None:
    source = [json.loads(line) for line in (FIXTURES / "contact.jsonl").read_text().splitlines()]
    source[1]["message"]["content"].append({"type":"future_blob","payload":{"keep":"everything"}})
    source.append({"type":"future_event","trace_id":"trace-contact","new_field":123})
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps(row)+"\n" for row in source))
    trace = adapt_trace(path)
    assert trace.metadata["events"]["1"]["message"]["content"][-1]["payload"] == {"keep":"everything"}
    assert trace.metadata["events"][str(len(source)-1)]["new_field"] == 123
    assert trace.metadata["unmapped_content"]
    assert trace.metadata["unmapped_event_indices"][-1] == len(source)-1


def test_tool_id_mismatch_is_rejected(tmp_path: Path) -> None:
    source = [json.loads(line) for line in (FIXTURES / "contact.jsonl").read_text().splitlines()]
    source[4]["message"]["content"][0]["tool_use_id"] = "not-a-real-call"
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps(row)+"\n" for row in source))
    with pytest.raises(ValueError, match="tool"):
        adapt_trace(path)


def test_foreign_sidecar_is_rejected() -> None:
    with pytest.raises(ValueError, match="trace"):
        adapt_trace(FIXTURES / "contact.jsonl", sidecar_path=FIXTURES / "email.sidecar.jsonl")


def test_later_grading_result_is_selected_and_history_retained(tmp_path: Path) -> None:
    source = [json.loads(line) for line in (FIXTURES / "contact.jsonl").read_text().splitlines()]
    last = {**source[-1], "task_score": 0.9}
    source.append(last)
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps(row)+"\n" for row in source))
    trace = adapt_trace(path)
    assert trace.metadata["official_result"]["task_score"] == 0.9
    assert len(trace.metadata["grading_history"]) == 2


def test_mixed_blocks_preserve_text_and_error_flags(tmp_path: Path) -> None:
    source = [json.loads(line) for line in (FIXTURES / "contact.jsonl").read_text().splitlines()]
    source[4]["message"]["content"][0]["is_error"] = True
    source[4]["message"]["content"].append({"type":"text","text":"Additional user context"})
    source[5]["message"]["reasoning_content"] = "  exact reasoning\n"
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps(row)+"\n" for row in source))
    trace = adapt_trace(path)
    assert any(row["role"] == "user" and row["content"] == "Additional user context" for row in trace.messages)
    assert any(row.get("reasoning_content") == "  exact reasoning\n" for row in trace.messages)
    assert trace.metadata["events"]["4"]["message"]["content"][0]["is_error"] is True


def _synthetic(tmp_path: Path, blocks: list[tuple[str, list[dict[str, Any]]]]) -> Path:
    """Write a minimal synthetic trace from (role, content-blocks) pairs."""
    rows: list[dict[str, Any]] = [{"type": "trace_start", "trace_id": "t", "task_id": "T"}]
    rows += [{"type": "message", "trace_id": "t", "message": {"role": r, "content": c}} for r, c in blocks]
    rows.append({"type": "trace_end", "trace_id": "t"})
    path = tmp_path / "synthetic.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_trace_without_tool_calls(tmp_path: Path) -> None:
    trace = adapt_trace(_synthetic(tmp_path, [
        ("user", [{"type": "text", "text": "hi"}]), ("assistant", [{"type": "text", "text": "hello"}])]))
    assert [m["role"] for m in trace.messages] == ["user", "assistant"]
    assert not any("tool_calls" in m for m in trace.messages)


def test_empty_content_is_kept_not_dropped(tmp_path: Path) -> None:
    trace = adapt_trace(_synthetic(tmp_path, [("user", [{"type": "text", "text": "hi"}]), ("assistant", [])]))
    assert trace.messages[-1] == {"role": "assistant", "content": ""}
    assert not trace.metadata["unmapped_content"]


def test_parallel_tool_calls_pair_by_id_in_order(tmp_path: Path) -> None:
    use = lambda i: {"type": "tool_use", "id": i, "name": "f", "input": {"k": i}}
    res = lambda i, text, err: {"type": "tool_result", "tool_use_id": i, "content": [{"type": "text", "text": text}], "is_error": err}
    trace = adapt_trace(_synthetic(tmp_path, [
        ("user", [{"type": "text", "text": "go"}]),
        ("assistant", [use("a"), use("b")]),
        ("user", [res("b", "second", True), res("a", "first", False)]),
        ("assistant", [{"type": "text", "text": "done"}])]))
    assistant = trace.messages[1]
    assert [c["id"] for c in assistant["tool_calls"]] == ["a", "b"]
    assert assistant["content"] is None
    tools = [m for m in trace.messages if m["role"] == "tool"]
    assert [(m["tool_call_id"], m["content"]) for m in tools] == [("b", "second"), ("a", "first")]
    assert trace.metadata["events"]["3"]["message"]["content"][0]["is_error"] is True


def test_unanswered_parallel_call_is_rejected(tmp_path: Path) -> None:
    use = lambda i: {"type": "tool_use", "id": i, "name": "f", "input": {}}
    path = _synthetic(tmp_path, [("user", [{"type": "text", "text": "go"}]), ("assistant", [use("a"), use("b")]),
        ("user", [{"type": "tool_result", "tool_use_id": "a", "content": [{"type": "text", "text": "x"}]}]),
        ("assistant", [{"type": "text", "text": "done"}])])
    with pytest.raises(ValueError, match="incomplete|no corresponding"):
        adapt_trace(path)
