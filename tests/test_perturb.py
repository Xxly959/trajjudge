"""Offline tests for perturbations and the defended template."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from openjudge.graders.agent import TrajectoryAccuracyGrader, TrajectoryComprehensiveGrader
from openjudge.models.schema.prompt_template import LanguageEnum

from trajjudge.adapter import adapt_trace
from trajjudge.perturb import DEFENSE_NOTICE, LOCATIONS, TEMPLATES, defended_template, inject

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"


@pytest.fixture
def messages() -> list[dict]:
    return adapt_trace(FIXTURES / "email.jsonl", sidecar_path=FIXTURES / "email.sidecar.jsonl").messages


def test_levels_are_ordered_and_texts_benign() -> None:
    assert [t.level for t in TEMPLATES] == [1, 2, 3, 4]
    assert len({t.text for t in TEMPLATES}) == 4
    for t in TEMPLATES:
        assert "http" not in t.text and "key" not in t.text.lower()


@pytest.mark.parametrize("location", LOCATIONS)
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.template_id)
def test_inject_changes_exactly_one_message_and_not_the_input(messages, template, location) -> None:
    before = copy.deepcopy(messages)
    out, record = inject(messages, template.template_id, location)
    assert messages == before
    changed = [i for i, (a, b) in enumerate(zip(before, out)) if a != b]
    assert changed == [record["message_index"]] and len(out) == len(before)
    assert out[changed[0]]["content"].endswith(template.text)
    assert out[changed[0]]["role"] == ("tool" if location == "tool_result" else "assistant")
    assert out[changed[0]].get("tool_call_id") == before[changed[0]].get("tool_call_id")


def test_no_insertion_point_is_an_error() -> None:
    with pytest.raises(ValueError):
        inject([{"role": "user", "content": "hi"}], "L1_note", "tool_result")
    with pytest.raises(ValueError):
        inject([{"role": "user", "content": "hi"}], "L1_note", "bogus")


@pytest.mark.parametrize("cls", [TrajectoryAccuracyGrader, TrajectoryComprehensiveGrader])
def test_defended_template_adds_notice_without_mutating_default(cls) -> None:
    default = cls.DEFAULT_TEMPLATE
    before = default.model_dump()
    new = defended_template(default)
    assert default.model_dump() == before
    system = [m for m in new.messages[LanguageEnum.EN] if m.role == "system"][0]
    assert DEFENSE_NOTICE in system.content
