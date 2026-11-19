"""Offline unit tests for P1 foundation: τ-bench adapter, multi-vendor providers, P1-5 held-out suite, and P1-6 ablations."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest

import trajjudge.grounded_judge as grounded_judge_mod
from trajjudge.config import Settings, load_provider_settings
from trajjudge.grounded_judge import (
    ABLATION_MODES,
    PROMPT_VARIANTS,
    build_audit_messages,
    extract_evidence_ledger,
    grade_trajectory_grounded,
    validate_and_score_grounded,
)
from trajjudge.llm import LLMClient
from trajjudge.perturb_v3 import (
    HELD_OUT_TEST_TEMPLATES,
    LOCATIONS_V3,
    held_out_suite_sha256,
    inject_v3,
)
from trajjudge.taubench_adapter import (
    adapt_taubench_record,
    load_taubench_file,
    select_best_of_n_tasks,
    select_taubench_cohort,
)


def _sample_tau_record(task_id: int, trial: int, reward: float, *, domain: str = "retail", model: str = "gpt-4o") -> dict[str, Any]:
    return {
        "task_id": task_id,
        "trial": trial,
        "domain": domain,
        "model": model,
        "reward": reward,
        "info": {
            "reward_action": reward,
            "reward_output": 1.0,
            "task": {
                "instruction": "Cancel order #W123 only after confirming reason with customer.",
                "actions": [{"name": "cancel_pending_order", "kwargs": {"order_id": "#W123", "reason": "no longer needed"}}],
                "outputs": [],
            },
        },
        "traj": [
            {"role": "system", "content": "You are a retail support agent. Always confirm before mutating orders."},
            {"role": "user", "content": f"Hi, please help me cancel order #W{task_id}."},
            {
                "role": "assistant",
                "content": "Let me look up your order first.",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "get_order_details", "arguments": json.dumps({"order_id": f"#W{task_id}"})}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "get_order_details", "content": '{"status": "pending", "items": ["hat"]}'},
            {
                "role": "assistant",
                "content": "Canceling now.",
                "tool_calls": [
                    {"id": "c2", "type": "function", "function": {"name": "cancel_pending_order", "arguments": json.dumps({"order_id": f"#W{task_id}"})}}
                ],
            },
            {"role": "tool", "tool_call_id": "c2", "name": "cancel_pending_order", "content": '{"status": "cancelled"}'},
            {"role": "assistant", "content": f"Order #W{task_id} has been cancelled."},
        ],
    }


# ------------------------------------------------------------------ P1-1 τ-bench adapter


def test_taubench_adapter_normalizes_and_quarantines_ground_truth(tmp_path: Path) -> None:
    rec = _sample_tau_record(7, 0, 0.0)
    adapted = adapt_taubench_record(rec)
    assert adapted.scenario_id == "taubench:retail:7"
    assert adapted.objective_pass is False
    assert adapted.metadata["total_tool_calls"] == 2
    assert adapted.metadata["mutating_tool_calls"] == 1
    assert adapted.privileged_outcome["expected_actions"][0]["name"] == "cancel_pending_order"

    # Ground-truth reward/expected_actions must NEVER appear in messages passed to judges
    msg_blob = json.dumps(adapted.messages)
    assert "reward_action" not in msg_blob
    assert "expected_actions" not in msg_blob
    assert "only after confirming reason" not in msg_blob

    # JSON list & JSONL loading both work identically
    jpath = tmp_path / "retail_gpt4o.json"
    jpath.write_text(json.dumps([rec]), encoding="utf-8")
    jlpath = tmp_path / "retail_gpt4o.jsonl"
    jlpath.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert load_taubench_file(jpath)[0].trace_id == load_taubench_file(jlpath)[0].trace_id


def test_select_taubench_cohort_and_best_of_n_targets() -> None:
    # Build 70 independent scenarios × 4 trials (2 fail, 2 pass each) = 280 traces
    traces = []
    for tid in range(70):
        dom = "retail" if tid < 45 else "airline"
        for trial in range(4):
            reward = 1.0 if trial % 2 == 0 else 0.0
            traces.append(adapt_taubench_record(_sample_tau_record(tid, trial, reward, domain=dom, model="agent-a")))

    cohort = select_taubench_cohort(traces, target_failures=100, target_passes=100, min_scenarios=60, seed=42)
    assert cohort["meets_p1_target"] is True
    assert cohort["n_failures"] == 100
    assert cohort["n_passes"] == 100
    assert cohort["n_scenarios"] == 70

    bon = select_best_of_n_tasks(traces, n_candidates=4, max_tasks=60)
    assert len(bon) == 60
    assert all(t["n_candidates"] == 4 and t["mixed_outcomes"] is True and t["oracle_pass"] is True for t in bon)


# ------------------------------------------------------------------ P1-5 held-out attack suite


def test_held_out_attack_suite_has_15_templates_3_locations_and_zero_leakage() -> None:
    assert len(HELD_OUT_TEST_TEMPLATES) >= 12
    assert len({t.template_id for t in HELD_OUT_TEST_TEMPLATES}) == len(HELD_OUT_TEST_TEMPLATES)
    assert len(held_out_suite_sha256()) == 64

    messages = adapt_taubench_record(_sample_tau_record(1, 0, 0.0)).messages
    for loc in LOCATIONS_V3:
        perturbed, rec = inject_v3(messages, HELD_OUT_TEST_TEMPLATES[0].template_id, loc)
        assert rec["location"] == loc
        assert rec["split"] == "test"
        assert HELD_OUT_TEST_TEMPLATES[0].text in perturbed[rec["message_index"]]["content"]
        # Input must not be mutated
        assert HELD_OUT_TEST_TEMPLATES[0].text not in messages[rec["message_index"]]["content"]

    # Leakage guard: grounded_judge.py and all prompt variants share zero >=3-word English spans with ANY held-out template
    def _words(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    source_norm = " ".join(_words(inspect.getsource(grounded_judge_mod)))
    for tpl in HELD_OUT_TEST_TEMPLATES:
        tokens = _words(tpl.text)
        for i in range(len(tokens) - 2):
            trigram = " ".join(tokens[i : i + 3])
            assert trigram not in source_norm, (
                f"Held-out template leakage: 3-word span {trigram!r} from {tpl.template_id} found in grounded_judge.py"
            )


# ------------------------------------------------------------------ P1-4 multi-vendor providers


def test_multi_vendor_provider_loading_and_thinking_style(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope-token")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-zhipu-token")

    qwen = load_provider_settings("qwen", env_file=tmp_path / "missing.env")
    assert qwen.provider == "qwen" and qwen.thinking_style == "dashscope" and qwen.judge_model == "qwen-plus"

    glm = load_provider_settings("glm", env_file=tmp_path / "missing.env")
    assert glm.provider == "glm" and glm.thinking_style == "none" and glm.judge_model == "glm-4.5"

    # Verify LLMClient sends provider-appropriate extra_body (and omits it for thinking_style="none")
    seen_requests: list[dict[str, Any]] = []

    def fake_transport(req: dict[str, Any]) -> dict[str, Any]:
        seen_requests.append(req)
        return {
            "id": "mock",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    pricing = tmp_path / "p.yaml"
    pricing.write_text(
        "currency: USD\nper: 1M_tokens\nmodels:\n  qwen-plus:\n    input_per_mtok: 0.5\n    output_per_mtok: 1.5\n"
        "  glm-4.5:\n    input_per_mtok: 0.5\n    output_per_mtok: 1.5\n",
        encoding="utf-8",
    )
    qwen_s = Settings(
        api_key="k", base_url=qwen.base_url, judge_model="qwen-plus", agent_model="qwen-plus",
        judge_thinking=False, agent_thinking=False, cache_dir=tmp_path / "c1",
        usage_log=tmp_path / "u1.jsonl", pricing_file=pricing, provider="qwen", thinking_style="dashscope",
    )
    glm_s = Settings(
        api_key="k", base_url=glm.base_url, judge_model="glm-4.5", agent_model="glm-4.5",
        judge_thinking=False, agent_thinking=False, cache_dir=tmp_path / "c2",
        usage_log=tmp_path / "u2.jsonl", pricing_file=pricing, provider="glm", thinking_style="none",
    )
    LLMClient(qwen_s, transport=fake_transport).complete([{"role": "user", "content": "hi"}])
    LLMClient(glm_s, transport=fake_transport).complete([{"role": "user", "content": "hi"}])

    assert seen_requests[0]["extra_body"] == {"enable_thinking": False}
    assert "extra_body" not in seen_requests[1]


# ------------------------------------------------------------------ P1-6 ablations & prompt variants


def test_grounded_ablation_modes_and_prompt_variants(settings: Settings) -> None:
    messages = adapt_taubench_record(_sample_tau_record(2, 0, 0.0)).messages
    # no_quarantine strips <untrusted_tool_data> tags
    ledger_nq = extract_evidence_ledger(messages, quarantine=False)
    assert all("<untrusted_tool_data" not in ev["quarantined_data"] for ev in ledger_nq["tool_events"])

    # no_ledger sends raw_messages directly
    msgs_nl = build_audit_messages(extract_evidence_ledger(messages), ablation="no_ledger", raw_messages=messages)
    assert '"raw_messages"' in msgs_nl[1]["content"]

    # no_veto respects model's pass even when an obligation is omitted
    raw_inconsistent = {
        "obligations": [
            {"id": "O1", "requirement": "Confirm before cancel", "status": "omitted", "evidence_indices": [1], "note": "Skipped"},
        ],
        "unauthorized_side_effect": False,
        "critical_defect": None,
        "verdict": "pass",
        "reason": "Model mistakenly said pass.",
    }
    ledger = extract_evidence_ledger(messages)
    assert validate_and_score_grounded(raw_inconsistent, ledger, apply_veto=True)["verdict"] == "fail"
    assert validate_and_score_grounded(raw_inconsistent, ledger, apply_veto=False)["verdict"] == "pass"

    # End-to-end check across all ablation modes and prompt variants
    valid_reply = {
        "id": "m",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(raw_inconsistent)},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 40},
    }
    client = LLMClient(settings, transport=lambda req: valid_reply)
    for mode in ABLATION_MODES:
        row = grade_trajectory_grounded("t-ab", messages, client, ablation=mode)
        assert row["status"] == "ok" and row["ablation"] == mode
        if mode == "no_veto":
            assert row["audit"]["verdict"] == "pass"
        else:
            assert row["audit"]["verdict"] == "fail"
    for pv in PROMPT_VARIANTS:
        row = grade_trajectory_grounded("t-pv", messages, client, prompt_variant=pv)
        assert row["status"] == "ok" and row["prompt_variant"] == pv
