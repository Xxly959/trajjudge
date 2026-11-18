"""Offline unit tests for Stage 3 and Neutral Control analysis logic."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_driver():
    spec = importlib.util.spec_from_file_location("run_stage3_and_neutral", ROOT / "scripts/run_stage3_and_neutral.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_stage3_and_neutral"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_neutral_control_attribution_distinguishes_framing_from_dilution() -> None:
    drv = _load_driver()
    traces = {f"t{i}": {"task_id": f"task_{i}", "messages": []} for i in range(6)}
    scenarios = {f"task_{i}": f"scen_{i}" for i in range(6)}

    p4_rows = []
    neu_rows = []
    for i in range(6):
        tid = f"t{i}"
        # Undefended inflates by +0.10; Neutral also inflates by +0.09 (no dilution effect);
        # Security reduces delta to +0.01 -> clear instruction_hierarchy_framing!
        p4_rows.extend([
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": False, "variant": "original", "status": "ok", "score": 0.70},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": False, "variant": "L3_notice/tool_result", "status": "ok", "score": 0.80 + 0.004 * i},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": True, "variant": "original", "status": "ok", "score": 0.70},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": True, "variant": "L3_notice/tool_result", "status": "ok", "score": 0.71 + 0.001 * i},
        ])
        neu_rows.extend([
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": "neutral", "variant": "original", "status": "ok", "score": 0.70},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": "neutral", "variant": "L3_notice/tool_result", "status": "ok", "score": 0.79 + 0.004 * i},
        ])

    res = drv.analyze_neutral_control(neu_rows, p4_rows, traces, scenarios)
    assert res["paired_three_way"]["n_traj"] == 6
    assert res["paired_three_way"]["n_scenarios"] == 6
    assert res["attribution"] == "instruction_hierarchy_framing"
    assert res["arms"]["undefended"]["asr"] == 1.0
    assert res["arms"]["neutral"]["asr"] == 1.0


def test_neutral_control_detects_pure_length_dilution() -> None:
    drv = _load_driver()
    traces = {f"t{i}": {"task_id": f"task_{i}", "messages": []} for i in range(6)}
    scenarios = {f"task_{i}": f"scen_{i}" for i in range(6)}

    p4_rows, neu_rows = [], []
    for i in range(6):
        tid = f"t{i}"
        # Both Neutral and Security reduce delta identically (+0.10 -> +0.01)
        p4_rows.extend([
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": False, "variant": "original", "status": "ok", "score": 0.70},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": False, "variant": "L3_notice/tool_result", "status": "ok", "score": 0.80 + 0.005 * i},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": True, "variant": "original", "status": "ok", "score": 0.70},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": True, "variant": "L3_notice/tool_result", "status": "ok", "score": 0.71 + 0.002 * i},
        ])
        neu_rows.extend([
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": "neutral", "variant": "original", "status": "ok", "score": 0.70},
            {"trace_id": tid, "grader": "trajectory_comprehensive", "repeat_id": 0, "defended": "neutral", "variant": "L3_notice/tool_result", "status": "ok", "score": 0.71 + 0.002 * i},
        ])

    res = drv.analyze_neutral_control(neu_rows, p4_rows, traces, scenarios)
    assert res["attribution"] == "length_dilution"


def test_pro_factorial_contrasts_measure_scale_and_architecture_gains() -> None:
    spec = importlib.util.spec_from_file_location("run_pro_factorial", ROOT / "scripts/run_pro_factorial.py")
    assert spec and spec.loader
    fac = importlib.util.module_from_spec(spec)
    sys.modules["run_pro_factorial"] = fac
    spec.loader.exec_module(fac)

    traces = {f"t{i}": {"task_id": f"task_{i}", "messages": []} for i in range(6)}
    scenarios = {f"task_{i}": f"scen_{i}" for i in range(6)}
    cohort = {f"t{i}": {"human_pass": False} for i in range(6)}
    preds = {
        "flash_accuracy": {f"t{i}": True for i in range(6)},        # misses 6/6
        "flash_grounded": {f"t{i}": (i >= 2) for i in range(6)},    # catches 2/6
        "pro_accuracy": {f"t{i}": (i >= 1) for i in range(6)},      # catches 1/6
        "pro_grounded": {f"t{i}": (i >= 5) for i in range(6)},      # catches 5/6
    }
    contrasts = fac.factorial_contrasts(preds, cohort, traces, scenarios)
    assert contrasts["n_common_traj"] == 6
    assert contrasts["arch_effect_on_pro_fail_recall"]["mean_gain"] > 0.5
    assert contrasts["combined_pro_grounded_vs_flash_generic_fail_recall"]["mean_gain"] > 0.8
