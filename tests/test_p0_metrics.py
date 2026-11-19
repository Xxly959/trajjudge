"""Offline unit tests for P0-3 (revised ASR + noise floor + schema retries) and P0-4 (ROC/PR + McNemar)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from trajjudge.calibration import exact_mcnemar, pr_curve_fail, recall_at_fpr, roc_curve_fail
from trajjudge.config import Settings
from trajjudge.judging import JudgeConfig, judge_once
from trajjudge.llm import LLMClient
from trajjudge.scenario_stats import injection_metrics_v3, noise_floor_from_repeats, normalized_delta


# ------------------------------------------------------------------ P0-4 tests


def test_roc_and_pr_curves_perfect_failure_separator() -> None:
    # Lower score = failure. Fails have scores 0.1, 0.2; passes have 0.8, 0.9.
    truth_pass = [False, False, True, True]
    scores = [0.1, 0.2, 0.8, 0.9]
    roc = roc_curve_fail(truth_pass, scores)
    assert roc[0]["fpr"] == 0.0 and roc[0]["tpr"] == 0.0
    assert roc[-1]["fpr"] == 1.0 and roc[-1]["tpr"] == 1.0
    assert recall_at_fpr(truth_pass, scores, 0.0) == {"step": 1.0, "interpolated": 1.0}
    assert recall_at_fpr(truth_pass, scores, 0.10) == {"step": 1.0, "interpolated": 1.0}
    pr = pr_curve_fail(truth_pass, scores)
    assert pr[-1]["recall"] == 1.0 and pr[-1]["precision"] == 0.5


def test_recall_at_fpr_handles_tied_scores_conservatively_vs_interpolated() -> None:
    # 1 fail at 0.2, 1 fail tied with 4 passes at 1.0.
    truth_pass = [False, False, True, True, True, True]
    scores = [0.2, 1.0, 1.0, 1.0, 1.0, 1.0]
    res = recall_at_fpr(truth_pass, scores, 0.20)
    # Strictly achievable with FPR <= 0.20 is threshold 0.2 -> TPR=0.5, FPR=0.0.
    assert res["step"] == pytest.approx(0.5)
    # Linear interpolation from (0.0, 0.5) to (1.0, 1.0) at x=0.20 gives 0.6.
    assert res["interpolated"] == pytest.approx(0.6)


def test_roc_empty_when_single_class() -> None:
    assert roc_curve_fail([True, True], [0.8, 0.9]) == []
    assert recall_at_fpr([True, True], [0.8, 0.9], 0.10) == {"step": None, "interpolated": None}


def test_exact_mcnemar_known_values() -> None:
    # 10 items, all failures: A catches 0, B catches 6 -> discordant=6 (0 vs 6), two-sided p = 2 / 2^6 = 1/32
    truth = [False] * 10
    pred_a = [True] * 10
    pred_b = [False] * 6 + [True] * 4
    res = exact_mcnemar(truth, pred_a, pred_b, fail_only=True)
    assert res["a_only_correct"] == 0
    assert res["b_only_correct"] == 6
    assert res["exact_p"] == pytest.approx(2 / 64)
    assert res["diff_b_minus_a"] == pytest.approx(0.6)

    # Zero discordant pairs -> p = 1.0
    same = exact_mcnemar(truth, pred_a, pred_a, fail_only=True)
    assert same["exact_p"] == 1.0


# ------------------------------------------------------------------ P0-3 tests


def test_normalized_delta_uses_grader_scale() -> None:
    assert normalized_delta("trajectory_accuracy", 1.0) == pytest.approx(0.5)
    assert normalized_delta("trajectory_comprehensive", 0.10) == pytest.approx(0.10)
    assert normalized_delta("evidence_grounded", -0.25) == pytest.approx(-0.25)


def test_noise_floor_and_injection_metrics_v3() -> None:
    # Two traces across two scenarios, each with 2 unperturbed repeats + 1 perturbed arm
    rows = [
        # Originals (repeat 0 and 1): trace t1 fluctuates 0.7 -> 0.8, t2 stays 0.4 -> 0.4
        {"trace_id": "t1", "grader": "trajectory_comprehensive", "defended": False, "judge_model": "m", "variant": "original", "repeat_id": 0, "status": "ok", "score": 0.70},
        {"trace_id": "t1", "grader": "trajectory_comprehensive", "defended": False, "judge_model": "m", "variant": "original", "repeat_id": 1, "status": "ok", "score": 0.80},
        {"trace_id": "t2", "grader": "trajectory_comprehensive", "defended": False, "judge_model": "m", "variant": "original", "repeat_id": 0, "status": "ok", "score": 0.40},
        {"trace_id": "t2", "grader": "trajectory_comprehensive", "defended": False, "judge_model": "m", "variant": "original", "repeat_id": 1, "status": "ok", "score": 0.40},
        # Perturbed (repeat 0): t1 stays 0.75 (+0.05), t2 flips 0.40 -> 0.65 (fail->pass!)
        {"trace_id": "t1", "grader": "trajectory_comprehensive", "defended": False, "judge_model": "m", "variant": "L3/tool", "repeat_id": 0, "status": "ok", "score": 0.75},
        {"trace_id": "t2", "grader": "trajectory_comprehensive", "defended": False, "judge_model": "m", "variant": "L3/tool", "repeat_id": 0, "status": "ok", "score": 0.65},
    ]
    clusters = {"t1": "s1", "t2": "s2"}
    nf = noise_floor_from_repeats(rows, clusters, resamples=100, seed=0)
    arm_nf = nf[("trajectory_comprehensive", False)]
    # 4 ordered pairs: t1 (0.7->0.8 inflated, 0.8->0.7 not), t2 (0.4->0.4 equal x2) -> 1/4 = 0.25
    assert arm_nf["n_ordered_pairs"] == 4
    assert arm_nf["score_inflation_noise_floor"] == pytest.approx(0.25)
    assert arm_nf["decision_flip_noise_floor"] == pytest.approx(0.0)

    rep = injection_metrics_v3(rows, clusters, resamples=100, seed=0)
    assert len(rep["arms"]) == 1
    arm = rep["arms"][0]
    assert arm["n_valid_pairs"] == 2
    assert arm["base_fail_pairs"] == 1
    assert arm["fail_to_pass_count"] == 1
    assert arm["decision_flip_rate"] == pytest.approx(1.0)
    assert arm["decision_flip_case_study"] is True  # < 5 scenarios
    assert arm["mean_norm_delta"] == pytest.approx(0.15)
    assert arm["score_inflation_rate"] == pytest.approx(1.0)
    assert arm["noise_floor"]["score_inflation_noise_floor"] == pytest.approx(0.25)


def test_judge_once_schema_retries_and_json_schema_wire_format(settings: Settings) -> None:
    seen_formats: list[Any] = []
    attempt_counter = {"n": 0}
    messages = [
        {"role": "user", "content": "check weather"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "sunny"},
        {"role": "assistant", "content": "It is sunny."},
    ]

    def transport(req: dict[str, Any]) -> dict[str, Any]:
        seen_formats.append(req.get("response_format"))
        attempt_counter["n"] += 1
        if attempt_counter["n"] == 1:
            # First attempt returns malformed accuracy score (99 -> rejected by check_raw)
            body = {"score": 99, "reason": "bad clamped score"}
        else:
            body = {"score": 2, "reason": "valid second attempt"}
        return {
            "id": f"mock-{attempt_counter['n']}",
            "object": "chat.completion",
            "created": 1,
            "model": settings.judge_model,
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(body)},
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
        }

    client = LLMClient(settings, transport=transport)
    cfg = JudgeConfig("trajectory_accuracy", False, "direct", 1, defended="neutral")
    row = judge_once("t1", messages, cfg, client, 0, "abc123", use_json_schema=True, schema_retries=1)
    assert row["status"] == "ok"
    assert row["score"] == 2.0
    assert row["schema_retry_attempts"] == 1
    assert row["usage"]["api_calls"] == 2
    assert all(isinstance(fmt, dict) and fmt.get("type") == "json_schema" for fmt in seen_formats)
