"""Known-answer tests for metrics."""

from __future__ import annotations

import pytest

from trajjudge import metrics as m


def test_kappa_known_values() -> None:
    a = [True, True, False, False, True, False, True, False, True, True]
    b = [True, False, False, False, True, False, True, True, True, True]
    # observed 0.8; pa=pb=0.6 -> expected 0.52 -> kappa = (0.8-0.52)/0.48
    assert m.cohen_kappa(a, b) == pytest.approx((0.8 - 0.52) / 0.48)
    assert m.cohen_kappa([True] * 5, [True] * 5) is None
    assert m.cohen_kappa(a, a) == pytest.approx(1.0)
    assert m.pabak(a, b) == pytest.approx(0.6)


def test_confusion_accuracy_baselines() -> None:
    truth = [True, True, True, False]
    pred = [True, False, True, False]
    assert m.confusion(truth, pred) == {"tp": 2, "fp": 0, "fn": 1, "tn": 1}
    assert m.accuracy(truth, pred) == 0.75
    base = m.baselines(truth)
    assert base["always_pass"] == 0.75 and base["majority"] == 0.75 and 0.4 < base["random"] < 0.6


def test_spearman_ties_and_constant() -> None:
    assert m.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert m.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert m.spearman([1, 1, 2, 2], [1, 2, 1, 2]) == pytest.approx(0.0)
    assert m.spearman([1, 1, 1], [1, 2, 3]) is None


def test_bootstrap_ci_brackets_and_is_seeded() -> None:
    data = [1.0] * 30 + [0.0] * 10
    stat = lambda idx: sum(data[i] for i in idx) / len(idx)
    lo, hi = m.bootstrap_ci(stat, len(data), seed=1)
    assert lo < 0.75 < hi and (lo, hi) == m.bootstrap_ci(stat, len(data), seed=1)
    assert m.bootstrap_ci(lambda idx: None, 10) is None


def test_stability_summary_perfect_and_unstable() -> None:
    stable = {"a": [3, 3, 3], "b": [1, 1, 1], "c": [2, 2, 2], "d": [3, 3, 3]}
    s = m.stability_summary(stable, threshold=2)
    assert s["mean_sd"] == 0 and s["flip_rate"] == 0 and s["mean_spearman"] == pytest.approx(1.0)
    flaky = {"a": [3, 1, 3], "b": [1, 1, 1], "c": [2, 3, 2], "d": [3, 3, 3]}
    f = m.stability_summary(flaky, threshold=2)
    assert f["flip_rate"] == pytest.approx(0.25) and f["mean_sd"] > 0
    assert f["pairwise_disagreement"] == pytest.approx((0.25 + 0 + 0.25) / 3)
    with pytest.raises(ValueError):
        m.stability_summary({"a": [1]}, 2)


def test_auc_known_values() -> None:
    assert m.auc([True, True, False, False], [0.9, 0.8, 0.3, 0.1]) == 1.0
    assert m.auc([True, False], [0.5, 0.5]) == 0.5
    assert m.auc([True, True, False], [0.2, 0.9, 0.5]) == pytest.approx(0.5)
    assert m.auc([True, True], [1, 2]) is None
