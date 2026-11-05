"""Offline tests for the blind annotation kit."""

from __future__ import annotations

from pathlib import Path

import pytest

from trajjudge import annotation as kit


def test_blind_ids_distinct_and_hide_trace_id() -> None:
    ids = [f"trace-{i}" for i in range(50)]
    mapping = kit.blind_ids(ids, seed=7)
    assert len(set(mapping.values())) == 50
    assert all("trace" not in v for v in mapping.values())
    assert mapping == kit.blind_ids(list(reversed(ids)), seed=7)


def test_render_shows_no_scores_or_model_names() -> None:
    messages = [{"role": "user", "content": "Find David"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c", "type": "function", "function": {"name": "search", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "c", "name": "search", "content": "x" * 5000},
                {"role": "assistant", "content": "done"}]
    text = kit.render_trace(messages, prompt_criteria="be correct", blind_id="Babc")
    assert "Babc" in text and "tool call `search`" in text and "omitted" in text
    assert "score" not in text.lower() and "deepseek" not in text.lower()


def test_template_is_blank_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    kit.write_template(path, ["B1", "B2"])
    rows = kit.read_labels(path)
    assert all(r["label"] == "" and r["reason"] == "" for r in rows)
    assert kit.validate_labels(rows, ["B1", "B2"]) == []
    rows[0].update(label="maybe")
    rows[1].update(label="pass", reason="  ")
    problems = kit.validate_labels(rows, ["B1", "B2", "B3"])
    assert any("label must be" in p for p in problems)
    assert any("reason" in p for p in problems)
    assert any("missing row for B3" in p for p in problems)


def test_relabel_sample_subset() -> None:
    pick = kit.relabel_sample([f"B{i}" for i in range(30)], 10, seed=3)
    assert len(pick) == 10 and len(set(pick)) == 10


def test_full_view_keeps_decisive_tail() -> None:
    text = kit.render_trace([{"role": "tool", "content": "x" * 5000 + "DECISIVE_TAIL"}],
                            blind_id="B1", max_block_chars=None)
    assert "DECISIVE_TAIL" in text and "omitted" not in text


def test_template_never_overwrites_owner_labels(tmp_path: Path) -> None:
    path = tmp_path / "labels.csv"
    path.write_text("owner data")
    with pytest.raises(FileExistsError):
        kit.write_template(path, ["B1"])
    assert path.read_text() == "owner data"


def test_duplicate_label_rows_are_rejected() -> None:
    row = {"blind_id": "B1", "round": "1", "label": "", "reason": ""}
    assert any("duplicate" in p for p in kit.validate_labels([row, row], ["B1"]))


def test_interrupted_save_preserves_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "labels.csv"
    kit.write_template(path, ["B1"])
    before = path.read_bytes()
    def fail(*args: object) -> None:
        raise OSError("simulated crash before replace")
    monkeypatch.setattr("os.replace", fail)
    with pytest.raises(OSError):
        kit.save_labels(path, [{"blind_id": "B1", "label": "pass", "reason": "owner-entered"}])
    assert path.read_bytes() == before
