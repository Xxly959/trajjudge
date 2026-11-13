"""Scenario grouping must survive translation copies and mixed-type keywords."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest
import yaml

MOD = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build_scenario_map.py"))
build_map = MOD["build_map"]
structure_fingerprint = MOD["structure_fingerprint"]


def write_task(root: Path, task_id: str, *, language: str = "en", text: str = "do the thing",
               tools: tuple[str, ...] = ("gmail_list_messages",), keywords=("VPN", "MFA"),
               fixture_tags: int = 4, weight: float = 0.5) -> Path:
    task_dir = root / task_id
    (task_dir / "fixtures" / "kb").mkdir(parents=True, exist_ok=True)
    (task_dir / "fixtures" / "kb" / "articles.json").write_text(json.dumps([
        {"article_id": "a1", "title": text, "tags": [f"t{i}" for i in range(fixture_tags)], "views": 1567}
    ]))
    task = {
        "task_id": task_id,
        "task_name": "Ambiguous Contact",
        "version": "1.0",
        "category": "communication",
        "difficulty": "medium",
        "tags": ["email"],
        "services": [{"name": "gmail", "port": 9100, "command": "python mock_services/gmail/server.py",
                      "env": {"GMAIL_FIXTURES": f"tasks/{task_id}/fixtures/gmail/inbox.json"}}],
        "prompt": {"text": text, "language": language},
        "tools": [{"name": t, "description": text,
                   "input_schema": {"type": "object", "properties": {
                       "q": {"type": "string", "description": text}}}}
                  for t in tools],
        "tool_endpoints": [{"tool_name": t, "url": "http://localhost:9100/gmail", "method": "POST"} for t in tools],
        "environment": {"timeout_seconds": 300, "max_turns": 20},
        "scoring_components": [
            {"name": "reading", "weight": weight, "check": {"type": "tool_called", "tool_name": tools[0], "min_calls": 1}},
            {"name": "synthesis", "weight": weight, "check": {"type": "keywords_present", "keywords": list(keywords)}},
        ],
        "safety_checks": [{"type": "send_without_confirmation", "tool_name": tools[0], "description": text}],
        "judge_rubric": text,
        "reference_solution": text,
        "primary_dimensions": [{"name": "clarity"}],
    }
    (task_dir / "task.yaml").write_text(yaml.safe_dump(task, allow_unicode=True, sort_keys=False))
    return task_dir


def test_translation_copies_share_one_scenario(tmp_path):
    write_task(tmp_path, "T025zh_ambiguous_contact_email", language="zh", text="通知张经理", keywords=("VPN", "MFA"))
    write_task(tmp_path, "T026_ambiguous_contact_email", language="en", text="notify Manager Zhang", keywords=("VPN", "MFA"))
    records, problems = build_map(tmp_path, ["T025zh_ambiguous_contact_email", "T026_ambiguous_contact_email"])
    assert len({r["scenario_id"] for r in records}) == 1
    assert {r["scenario_id"] for r in records} == {"ambiguous_contact_email"}
    assert all(r["scenario_size"] == 2 for r in records)
    assert not problems


def test_translated_keywords_are_flagged_but_still_grouped(tmp_path):
    write_task(tmp_path, "T001zh_x", language="zh", keywords=("虚拟专用网",))
    write_task(tmp_path, "T002_x", language="en", keywords=("VPN",))
    records, problems = build_map(tmp_path, ["T001zh_x", "T002_x"])
    assert len({r["scenario_id"] for r in records}) == 1
    assert any("keywords_present" in p["issue"] for p in problems)


def test_different_tools_are_different_scenarios(tmp_path):
    """Regression: the name suffix alone must not pool distinct structures into one cluster."""
    write_task(tmp_path, "T001_x", tools=("gmail_list_messages",))
    write_task(tmp_path, "T002_x", tools=("kb_search",))
    records, problems = build_map(tmp_path, ["T001_x", "T002_x"])
    ids = {r["scenario_id"] for r in records}
    assert len(ids) == 2
    assert all(r["scenario_size"] == 1 for r in records)
    assert any("reused by structurally different tasks" in p["issue"] for p in problems)


def test_translated_schema_descriptions_do_not_split_scenarios(tmp_path):
    """Regression: tool input_schema carries translated descriptions, not structure."""
    write_task(tmp_path, "T001zh_x", language="zh", text="搜索联系人")
    write_task(tmp_path, "T002_x", language="en", text="search contacts")
    a = yaml.safe_load((tmp_path / "T001zh_x" / "task.yaml").read_text())
    b = yaml.safe_load((tmp_path / "T002_x" / "task.yaml").read_text())
    assert a["tools"][0]["input_schema"] != b["tools"][0]["input_schema"]
    assert structure_fingerprint(a) == structure_fingerprint(b)
    records, _ = build_map(tmp_path, ["T001zh_x", "T002_x"])
    assert len({r["scenario_id"] for r in records}) == 1


def test_fixture_shape_disagreement_is_flagged_and_visible(tmp_path):
    """Merging is the conservative choice, but it must be auditable, not silent."""
    write_task(tmp_path, "T001_x", fixture_tags=4)
    write_task(tmp_path, "T002_x", fixture_tags=5)
    records, problems = build_map(tmp_path, ["T001_x", "T002_x"])
    assert len({r["scenario_id"] for r in records}) == 1
    assert {r["fixture_match"] for r in records} == {"different"}
    assert len({r["fixture_shape_hash"] for r in records}) == 2
    assert any("fixture data shape" in p["issue"] for p in problems)


def test_fixture_shape_difference_requires_owner_confirmation(tmp_path):
    write_task(tmp_path, "T159zh_vip", fixture_tags=5)
    write_task(tmp_path, "T160_vip", fixture_tags=4)
    records, problems = build_map(tmp_path, ["T159zh_vip", "T160_vip"])
    assert len({r["scenario_id"] for r in records}) == 1
    shape = [p for p in problems if "fixture data shape" in p["issue"]]
    assert len(shape) == 1
    assert "owner confirmation" in shape[0]["recommendation"]


def test_mixed_type_keywords_do_not_crash(tmp_path):
    """Regression: keywords can contain ints, so sorting must not compare int to str."""
    write_task(tmp_path, "T001_x", keywords=(2024, "VPN"))
    write_task(tmp_path, "T002_x", keywords=(2024, "VPN"))
    records, problems = build_map(tmp_path, ["T001_x", "T002_x"])
    assert len({r["scenario_id"] for r in records}) == 1


def test_fixture_paths_containing_task_id_do_not_split_scenarios(tmp_path):
    write_task(tmp_path, "T001zh_x", language="zh")
    write_task(tmp_path, "T002_x", language="en")
    a = yaml.safe_load((tmp_path / "T001zh_x" / "task.yaml").read_text())
    b = yaml.safe_load((tmp_path / "T002_x" / "task.yaml").read_text())
    assert a["services"][0]["env"] != b["services"][0]["env"]
    assert structure_fingerprint(a) == structure_fingerprint(b)


def test_missing_task_definition_is_reported(tmp_path):
    write_task(tmp_path, "T001_x")
    records, problems = build_map(tmp_path, ["T001_x", "T999_missing"])
    assert len(records) == 1
    assert any(p["issue"] == "task.yaml missing" for p in problems)


def test_problems_are_deduplicated_per_pair(tmp_path):
    write_task(tmp_path, "T001zh_x", language="zh", keywords=("甲",), fixture_tags=5)
    write_task(tmp_path, "T002_x", language="en", keywords=("A",), fixture_tags=4)
    _, problems = build_map(tmp_path, ["T001zh_x", "T002_x"])
    keys = [(tuple(p["task_ids"]), p["issue"]) for p in problems]
    assert len(keys) == len(set(keys))