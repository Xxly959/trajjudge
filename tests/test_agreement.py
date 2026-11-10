"""Tests for the RQ1 analysis on synthetic rows (not experimental data)."""

from __future__ import annotations

import pytest

from trajjudge.agreement import agreement_report, self_consistency


def rows() -> list[dict]:
    out = []
    for i in range(40):
        human = i % 4 != 0
        out.append({"human": human, "official": human if i % 10 else not human, "category": "ab"[i % 2],
                    "scores": {"trajectory_accuracy": (3.0 if human else 1.0) if i % 8 else 2.0,
                               "trajectory_comprehensive": 0.9 if human else 0.2}})
    return out


def test_report_structure_and_values() -> None:
    rep = agreement_report(rows(), seed=1)
    assert rep["n"] == 40 and rep["labels"] == {"pass": 30, "fail": 10}
    acc = rep["graders"]["trajectory_accuracy"]
    assert acc["threshold"] == 2.0 and acc["n"] == 40
    assert acc["confusion"]["tp"] + acc["confusion"]["fn"] == 30
    assert acc["baselines"]["always_pass"] == pytest.approx(0.75)
    assert rep["graders"]["trajectory_comprehensive"]["accuracy"] == 1.0
    assert rep["graders"]["trajectory_comprehensive"]["auc"] == 1.0
    assert set(acc["per_category"]) == {"a", "b"}
    assert acc["accuracy_ci"][0] <= acc["accuracy"] <= acc["accuracy_ci"][1]
    assert rep == agreement_report(rows(), seed=1)


def test_error_rows_are_excluded_not_counted_as_zero() -> None:
    data = rows()
    data[0]["scores"]["trajectory_accuracy"] = None
    assert agreement_report(data)["graders"]["trajectory_accuracy"]["n"] == 39


def test_self_consistency() -> None:
    assert self_consistency({"a": True, "b": False, "c": True}, {"a": True, "b": False, "c": False})["agreement"] == pytest.approx(2 / 3)
    assert self_consistency({"a": True}, {"a": True}) is None
