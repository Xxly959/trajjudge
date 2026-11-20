"""Unit tests for paired ΔAUC, ITT imputation, and scenario-cluster bootstrap."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import paired_auc as pa  # noqa: E402


def _make_cohort() -> list[dict[str, object]]:
    # 6 scenarios, 2 traces each (12 total): first 3 scenarios fail, last 3 pass
    cohort = []
    for idx in range(6):
        sc = f"sc_{idx}"
        obj_pass = idx >= 3
        for t in range(2):
            cohort.append({
                "trace_id": f"tr_{idx}_{t}",
                "scenario_id": sc,
                "objective_pass": obj_pass,
            })
    return cohort


def test_roc_auc_fail_exact_and_ties() -> None:
    # Perfect separation
    assert pa.roc_auc_fail([True, True, False, False], [0.9, 0.8, 0.2, 0.1]) == 1.0
    # Reversed
    assert pa.roc_auc_fail([True, True, False, False], [0.1, 0.2, 0.8, 0.9]) == 0.0
    # All ties -> 0.5
    assert pa.roc_auc_fail([True, True, False, False], [0.5, 0.5, 0.5, 0.5]) == 0.5
    # Partial tie: pos=[0.8, 0.5], neg=[0.5, 0.2] -> pairs: (0.8>0.5, 0.8>0.2, 0.5==0.5, 0.5>0.2) = 3.5/4
    assert pa.roc_auc_fail([True, True, False, False], [0.8, 0.5, 0.5, 0.2]) == 0.875
    # Single class -> None
    assert pa.roc_auc_fail([True, True], [0.9, 0.1]) is None


def test_paired_delta_auc_complete_case_and_itt() -> None:
    cohort = _make_cohort()
    # Model A (grounded, [0,1]): perfect on valid rows, but misses 1 failing trace (error)
    # Model B (accuracy, [1,3]): all valid, assigns score=1 to fail, score=3 to pass except sc_3 has score=1
    rows_a = {}
    rows_b = {}
    for tr in cohort:
        tid = str(tr["trace_id"])
        is_pass = bool(tr["objective_pass"])
        rows_a[tid] = {"trace_id": tid, "grader": "evidence_grounded", "status": "ok", "score": 0.9 if is_pass else 0.1}
        rows_b[tid] = {"trace_id": tid, "grader": "trajectory_accuracy", "status": "ok", "score": 3.0 if is_pass else 1.0}
    # Inject one error in A on a PASSING trace (tr_4_0) -> ITT assigns score=0 (fail score=1.0), hurting A's AUC!
    rows_a["tr_4_0"] = {"trace_id": "tr_4_0", "grader": "evidence_grounded", "status": "error", "score": None}
    # Make B slightly imperfect on tr_0_0 so A beats B in complete-case
    rows_b["tr_0_0"]["score"] = 3.0

    cc = pa.compute_paired_delta_auc(cohort, rows_a, rows_b, mode="complete_case", resamples=300, seed=0)
    itt = pa.compute_paired_delta_auc(cohort, rows_a, rows_b, mode="itt", resamples=300, seed=0)

    assert cc["n_paired"] == 11
    assert cc["auc_a"] == 1.0
    assert cc["auc_b"] < 1.0
    assert cc["delta_auc"] > 0.0

    # Under ITT, tr_4_0 (truth=pass) gets raw_score=0.0 -> fail_score=1.0 > fail_score=0.9 of failing traces!
    assert itt["n_paired"] == 12
    assert itt["auc_a"] < 1.0
    # Verify accuracy ITT imputation uses raw_score=0.0 -> fail_score=3.0 (strictly higher than score=1 -> 2.0)
    assert pa.row_to_fail_score({"status": "error", "score": None}, "trajectory_accuracy", itt=True) == 3.0
    assert pa.row_to_fail_score({"status": "ok", "score": 1.0}, "trajectory_accuracy", itt=True) == 2.0


def test_cluster_bootstrap_keeps_scenarios_together() -> None:
    cohort = _make_cohort()
    rows_a = {
        str(tr["trace_id"]): {
            "trace_id": tr["trace_id"],
            "grader": "evidence_grounded",
            "status": "ok",
            "score": 0.9 if tr["objective_pass"] else 0.1,
        }
        for tr in cohort
    }
    rows_b = {
        str(tr["trace_id"]): {
            "trace_id": tr["trace_id"],
            "grader": "trajectory_comprehensive",
            "status": "ok",
            "score": 0.9 if tr["objective_pass"] else 0.1,
        }
        for tr in cohort
    }
    res = pa.compute_paired_delta_auc(cohort, rows_a, rows_b, mode="complete_case", resamples=200, seed=7)
    assert res["delta_auc"] == 0.0
    assert res["n_scenarios"] == 6
    assert res["ci_95"] == [0.0, 0.0]
    assert res["p_value"] == 1.0


def test_paired_auc_v3_report_privacy_and_shape(tmp_path: Path) -> None:
    rep_path = ROOT / "reports/paired_auc_v3.json"
    if not rep_path.is_file():
        return
    text = rep_path.read_text(encoding="utf-8")
    assert "tau_airline_" not in text and "tau_retail_" not in text
    data = json.loads(text)
    assert "main_cohort" in data and "ablation_60" in data
