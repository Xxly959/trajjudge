"""Unit tests for Module C P1-3 human review packet & summary aggregation."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import summarize_p13_review as sr  # noqa: E402


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def test_pending_review_does_not_fabricate_numbers(tmp_path: Path) -> None:
    bs = tmp_path / "bs.csv"
    cl = tmp_path / "cl.csv"
    out = tmp_path / "out.json"
    _write_csv(bs, ["trace_id", "domain", "scenario_id", "ai_defect_type", "human_verdict", "human_reason"], [
        ["tau_airline_12_t1_abc", "airline", "sc_1", "policy_violation", "", ""],
    ])
    _write_csv(cl, ["blind_id", "human_v2_label", "silver_label", "final_label", "favors", "human_reason"], [
        ["B407e62", "fail", "pass", "", "", ""],
    ])
    rep = sr.summarize_reviews(blindspot_csv=bs, claw_csv=cl, out_path=out)
    assert rep["status"] == "pending_human_review"
    assert rep["blindspots_c1"]["reviewed_count"] == 0
    assert rep["blindspots_c1"]["ai_blindspot_precision_over_13"] is None
    text = out.read_text(encoding="utf-8")
    assert "tau_airline_" not in text and "B407e62" not in text


def test_completed_review_calculates_precision_and_favors(tmp_path: Path) -> None:
    bs = tmp_path / "bs.csv"
    cl = tmp_path / "cl.csv"
    out = tmp_path / "out.json"
    _write_csv(bs, ["trace_id", "domain", "scenario_id", "ai_defect_type", "human_verdict", "human_reason"], [
        ["tau_1", "airline", "sc_1", "policy_violation", "confirmed", "missing user confirmation"],
        ["tau_2", "retail", "sc_2", "hallucinated_claim", "false_alarm", "supported by tool output"],
        ["tau_3", "retail", "sc_3", "db_check_blindspot", "confirmed", "wrong tracking id"],
    ])
    _write_csv(cl, ["blind_id", "human_v2_label", "silver_label", "final_label", "favors", "human_reason"], [
        ["B1", "fail", "pass", "pass", "", "ai was right on second reading"],
        ["B2", "pass", "fail", "pass", "human", "minor wording is acceptable"],
    ])
    rep = sr.summarize_reviews(blindspot_csv=bs, claw_csv=cl, out_path=out)
    assert rep["status"] == "completed"
    assert rep["blindspots_c1"]["verdict_counts"] == {"confirmed": 2, "false_alarm": 1, "unclear": 0}
    assert rep["blindspots_c1"]["ai_blindspot_precision_over_13"] == round(2 / 3, 4)
    assert rep["claw48_adjudication_c2"]["favors_counts"] == {"human": 1, "ai": 1, "other": 0}


def test_invalid_verdict_raises(tmp_path: Path) -> None:
    bs = tmp_path / "bs.csv"
    cl = tmp_path / "cl.csv"
    _write_csv(bs, ["trace_id", "domain", "scenario_id", "ai_defect_type", "human_verdict", "human_reason"], [
        ["tau_1", "airline", "sc_1", "policy_violation", "maybe", "reason"],
    ])
    _write_csv(cl, ["blind_id", "human_v2_label", "silver_label", "final_label", "favors", "human_reason"], [])
    with pytest.raises(ValueError, match="invalid human_verdict"):
        sr.summarize_reviews(blindspot_csv=bs, claw_csv=cl, out_path=None)
