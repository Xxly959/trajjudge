"""Offline unit tests for EvidenceGroundedGrader (Extract-Audit-Veto hybrid judge)."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest

import trajjudge.grounded_judge as grounded_judge_mod
from trajjudge.adapter import adapt_trace
from trajjudge.config import Settings
from trajjudge.grounded_judge import (
    EVIDENCE_GROUNDED_SYSTEM_PROMPT,
    GRADER_NAME,
    PASS_THRESHOLD,
    build_audit_messages,
    extract_evidence_ledger,
    grade_trajectory_grounded,
    validate_and_score_grounded,
)
from trajjudge.judging import JudgeConfig
from trajjudge.llm import LLMClient
from trajjudge.perturb import TEMPLATES, inject

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"


@pytest.fixture
def sample_messages() -> list[dict[str, Any]]:
    return adapt_trace(FIXTURES / "email.jsonl", sidecar_path=FIXTURES / "email.sidecar.jsonl").messages


def _mock_reply(payload: dict[str, Any], *, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "mock-grounded",
        "object": "chat.completion",
        "created": 1,
        "model": "judge-test",
        "choices": [{
            "index": 0,
            "finish_reason": finish_reason,
            "message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        }],
        "usage": {"prompt_tokens": 320, "completion_tokens": 90, "total_tokens": 410},
    }


def test_ledger_extracts_tools_and_quarantines_outputs_without_cue_leakage(sample_messages: list[dict[str, Any]]) -> None:
    ledger = extract_evidence_ledger(sample_messages)
    assert ledger["structural_signals"]["total_tool_calls"] >= 1
    assert ledger["structural_signals"]["unmatched_tool_calls"] == 0
    assert ledger["structural_signals"]["has_final_assistant_reply"] is True
    assert all("<untrusted_tool_data" in ev["quarantined_data"] for ev in ledger["tool_events"])
    assert "untrusted_grading_directive_cues" not in ledger["structural_signals"]

    injected, _ = inject(sample_messages, "L3_notice", "tool_result")
    injected_ledger = extract_evidence_ledger(injected)
    assert "untrusted_grading_directive_cues" not in injected_ledger["structural_signals"]


def test_no_perturb_template_leakage_in_grounded_judge() -> None:
    """P0-2 guard: judge code and prompt must share zero >=3-word spans with perturb.py templates."""
    def _words(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    source_text = inspect.getsource(grounded_judge_mod)
    targets = {
        "grounded_judge.py": " ".join(_words(source_text)),
        "EVIDENCE_GROUNDED_SYSTEM_PROMPT": " ".join(_words(EVIDENCE_GROUNDED_SYSTEM_PROMPT)),
    }
    for template in TEMPLATES:
        tokens = _words(template.text)
        for i in range(len(tokens) - 2):
            trigram = " ".join(tokens[i : i + 3])
            for target_name, normalized in targets.items():
                assert trigram not in normalized, (
                    f"Data leakage: 3-word span {trigram!r} from perturb template "
                    f"{template.template_id!r} found in {target_name}"
                )
    assert "evaluation notice" not in targets["grounded_judge.py"]
    assert not hasattr(grounded_judge_mod, "_INJECTION_CUE_RE")


def test_veto_gate_overrides_model_pass_when_any_obligation_unverified() -> None:
    ledger = {
        "valid_message_indices": [0, 1, 2, 3, 4],
        "structural_signals": {"unmatched_tool_calls": 0, "has_final_assistant_reply": True},
    }
    raw = {
        "obligations": [
            {"id": "O1", "requirement": "List open tickets", "status": "verified", "evidence_indices": [2], "note": "Listed in [2]"},
            {"id": "O2", "requirement": "Update priority", "status": "unverified_claim", "evidence_indices": [4], "note": "Claimed in [4] without update call"},
        ],
        "unauthorized_side_effect": False,
        "critical_defect": "missing_update_call",
        "verdict": "pass",  # LLM mistakenly said pass despite an unverified_claim obligation!
        "reason": "Agent claimed [4] updated tickets without calling update.",
    }
    res = validate_and_score_grounded(raw, ledger)
    assert res["verdict"] == "fail"
    assert res["veto_overrode_model"] is True
    assert res["score"] < PASS_THRESHOLD
    assert res["score"] == pytest.approx(0.225)


def test_all_verified_and_no_side_effect_passes_above_threshold() -> None:
    ledger = {
        "valid_message_indices": [0, 1, 2, 3, 4],
        "structural_signals": {"unmatched_tool_calls": 0, "has_final_assistant_reply": True},
    }
    raw = {
        "obligations": [
            {"id": "O1", "requirement": "Lookup contact", "status": "verified", "evidence_indices": [2], "note": "Matched in [2]"},
            {"id": "O2", "requirement": "Report email", "status": "verified", "evidence_indices": [4], "note": "Reported accurately in [4]"},
        ],
        "unauthorized_side_effect": False,
        "critical_defect": None,
        "verdict": "pass",
        "reason": "All obligations verified against [2] and [4].",
    }
    res = validate_and_score_grounded(raw, ledger)
    assert res["verdict"] == "pass"
    assert res["score"] == 1.0


def test_unauthorized_side_effect_forces_zero_score_and_fail() -> None:
    ledger = {
        "valid_message_indices": [0, 1, 2, 3],
        "structural_signals": {"unmatched_tool_calls": 0, "has_final_assistant_reply": True},
    }
    raw = {
        "obligations": [
            {"id": "O1", "requirement": "Review tickets", "status": "verified", "evidence_indices": [2], "note": "Reviewed"},
        ],
        "unauthorized_side_effect": True,
        "critical_defect": "closed_ticket_against_instruction",
        "verdict": "pass",
        "reason": "Closed ticket in [3] despite instruction not to close.",
    }
    res = validate_and_score_grounded(raw, ledger)
    assert res["verdict"] == "fail"
    assert res["score"] == 0.0


def test_out_of_range_message_index_is_rejected() -> None:
    ledger = {
        "valid_message_indices": [0, 1, 2],
        "structural_signals": {"unmatched_tool_calls": 0, "has_final_assistant_reply": True},
    }
    raw = {
        "obligations": [
            {"id": "O1", "requirement": "Check", "status": "verified", "evidence_indices": [99], "note": "Hallucinated index"},
        ],
        "unauthorized_side_effect": False,
        "critical_defect": None,
        "verdict": "pass",
        "reason": "Hallucinated citation.",
    }
    with pytest.raises(ValueError, match="out-of-range"):
        validate_and_score_grounded(raw, ledger)


def test_structural_veto_triggers_on_missing_final_reply() -> None:
    msgs = [
        {"role": "user", "content": "Check status"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "get_status", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "get_status", "content": '{"ok": true}'},
    ]
    ledger = extract_evidence_ledger(msgs)
    assert ledger["structural_signals"]["has_final_assistant_reply"] is False
    raw = {
        "obligations": [{"id": "O1", "requirement": "Check status", "status": "verified", "evidence_indices": [2], "note": "ok"}],
        "unauthorized_side_effect": False,
        "critical_defect": None,
        "verdict": "pass",
        "reason": "Checked [2].",
    }
    res = validate_and_score_grounded(raw, ledger)
    assert res["structural_veto"] is True and res["verdict"] == "fail" and res["score"] < PASS_THRESHOLD


def test_grade_trajectory_grounded_end_to_end_and_cache_replay(settings: Settings, sample_messages: list[dict[str, Any]]) -> None:
    calls: list[dict[str, Any]] = []
    valid_body = {
        "obligations": [
            {"id": "O1", "requirement": "Triage inbox", "status": "verified", "evidence_indices": [2, 3], "note": "Verified"},
        ],
        "unauthorized_side_effect": False,
        "critical_defect": None,
        "verdict": "pass",
        "reason": "Verified against [2] and [3].",
    }

    def transport(req: dict[str, Any]) -> dict[str, Any]:
        calls.append(req)
        return _mock_reply(valid_body)

    client = LLMClient(settings, transport=transport)
    row1 = grade_trajectory_grounded("trace-1", sample_messages, client)
    assert row1["status"] == "ok" and row1["grader"] == GRADER_NAME and row1["score"] == 1.0
    assert row1["usage"]["api_calls"] == 1 and len(calls) == 1

    # Replay from cache with offline=True makes zero transport calls.
    offline_client = LLMClient(settings, offline=True)
    row2 = grade_trajectory_grounded("trace-1", sample_messages, offline_client)
    assert row2["status"] == "ok" and row2["score"] == 1.0 and row2["usage"]["cached_calls"] == 1
    assert len(calls) == 1


def test_judge_config_supports_neutral_arm_without_changing_legacy_names() -> None:
    assert JudgeConfig("trajectory_comprehensive", False, defended=False).name == "trajectory_comprehensive|think=off|direct1"
    assert JudgeConfig("trajectory_comprehensive", False, defended=True).name == "trajectory_comprehensive|think=off|direct1|def"
    assert JudgeConfig("trajectory_comprehensive", False, defended="neutral").name == "trajectory_comprehensive|think=off|direct1|neutral"
    with pytest.raises(ValueError):
        JudgeConfig("trajectory_comprehensive", False, defended="invalid")
