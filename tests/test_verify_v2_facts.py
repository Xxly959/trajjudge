"""Fact-check helpers: known-answer statistics and upstream path resolution."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

MOD = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/verify_v2_facts.py"))
kappa = MOD["kappa"]
auc = MOD["auc"]
check = MOD["check"]
render_table = MOD["render_table"]
upstream_voting_path = MOD["upstream_voting_path"]


def test_kappa_known_answers():
    assert kappa(10, 0, 0, 10) == pytest.approx(1.0)
    assert kappa(10, 10, 0, 0) == pytest.approx(0.0)
    assert kappa(0, 0, 0, 0) is None


def test_kappa_degenerate_single_class_returns_none():
    assert kappa(20, 0, 0, 0) is None


def test_auc_known_answers():
    assert auc([(3.0, True), (1.0, False)]) == pytest.approx(1.0)
    assert auc([(1.0, True), (3.0, False)]) == pytest.approx(0.0)
    assert auc([(2.0, True), (2.0, False)]) == pytest.approx(0.5)
    assert auc([(1.0, True)]) is None


def test_upstream_path_resolves_from_relative_root(tmp_path, monkeypatch):
    """Regression: Path('.').parent is still '.', which silently lost the upstream file."""
    (tmp_path / "OpenJudge/openjudge/evaluation_strategy").mkdir(parents=True)
    target = tmp_path / "OpenJudge/openjudge/evaluation_strategy/voting_evaluation_strategy.py"
    target.write_text("tie_breaker = MIN\n")
    (tmp_path / "proj").mkdir()
    monkeypatch.chdir(tmp_path / "proj")
    assert upstream_voting_path(Path(".")) == target
    assert upstream_voting_path(Path(".").resolve()) == target


def test_check_records_disagreement_and_table_marks_it():
    facts = []
    check(facts, "x", "claim", {"a": 1}, {"a": 2}, False, "evidence.json")
    assert facts[0]["agrees"] is False
    table = render_table(facts)
    assert "| x | claim |" in table
    assert "NO" in table


def test_render_table_truncates_long_values():
    facts = []
    check(facts, "y", "claim", {"blob": "z" * 500}, None, True, "e")
    assert "..." in render_table(facts)