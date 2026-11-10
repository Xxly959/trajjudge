"""Known-answer offline analysis tests; synthetic inputs are not experiment evidence."""
import pytest

from trajjudge.analysis import stability_report, injection_report, join_labels, agreement_with_clusters


def row(trace, repeat, score, variant="original", status="ok"):
    return {"trace_id": trace, "repeat_id": repeat, "score": score, "variant": variant,
            "config": "accuracy|direct", "grader": "trajectory_accuracy", "judge_model": "test",
            "thinking": False, "max_tokens": 100, "status": status}


def test_stability_counts_missing_repeats_and_bootstraps() -> None:
    rows = [row("a", r, [1, 3, 1][r]) for r in range(3)] + [row("b", r, 3) for r in range(3)] + [row("c", 0, 1)]
    result = stability_report(rows, repeats=3, resamples=40)[0]
    assert result["complete_traces"] == 2 and result["incomplete_traces"] == 1
    assert result["summary"]["flip_rate"] == .5
    assert len(result["ci"]["flip_rate"]) == 2


def test_injection_pairs_repeat_and_keeps_missing_baselines() -> None:
    rows = [row("a", 0, 1), row("a", 0, 3, "L2/tool"), row("a", 1, 1),
            row("a", 1, 1, "L2/tool"), row("b", 0, 3, "L2/tool")]
    result = injection_report(rows, resamples=40)[0]
    assert result["paired_observations"] == 2 and result["unpaired_observations"] == 1
    assert result["traces"] == 1 and result["mean_inflation"] == 1
    assert result["baseline_fail_flip_rate"] == .5
    assert result["baseline_fail_observations"] == 2 and result["fail_to_pass_observations"] == 1
    assert result["changed_observations"] == 1


def test_injection_has_no_flip_rate_without_failed_baselines() -> None:
    result = injection_report([row("a", 0, 2), row("a", 0, 3, "L2/tool")], resamples=40)[0]
    assert result["paired_observations"] == 1 and result["changed_observations"] == 1
    assert result["baseline_fail_observations"] == result["fail_to_pass_observations"] == 0
    assert result["baseline_fail_flip_rate"] is None and result["flip_ci"] is None


def test_join_uses_only_owner_labels_and_reports_missing() -> None:
    candidates = [{"trace_id": "t", "passed": True, "category": "c", "task_id": "task"}]
    key = {"t": "B1"}
    blank = [{"blind_id": "B1", "round": "1", "label": "", "reason": ""}]
    assert join_labels(candidates, key, blank, [row("t", 0, 3)])["rows"] == []
    blank[0].update(label="fail", reason="synthetic owner fixture")
    joined = join_labels(candidates, key, blank, [row("t", 0, None, status="error")])
    assert joined["rows"][0]["human"] is False and joined["missing_scores"]["trajectory_accuracy"] == 1
    assert joined["rows"][0]["scores"] == {}


def test_duplicate_or_mixed_judge_rows_rejected() -> None:
    rows = [row("a", 0, 1), row("a", 0, 3)]
    with pytest.raises(ValueError, match="duplicate"):
        stability_report(rows)


def test_agreement_reports_task_clusters_and_category_intervals() -> None:
    rows = [{"task_id": f"task{i//2}", "category": "c", "human": i < 2, "official": i < 2,
             "scores": {"trajectory_accuracy": 3 if i < 2 else 1}} for i in range(4)]
    result = agreement_with_clusters(rows, resamples=40)
    assert result["bootstrap_clusters"] == 2
    assert result["graders"]["trajectory_accuracy"]["per_category"]["c"]["accuracy_ci"] == (1., 1.)


def test_extra_repeats_are_not_silently_truncated() -> None:
    rows = [row("a", i, score) for i, score in enumerate([1, 1, 1, 3, 3])]
    with pytest.raises(ValueError, match="repeat"):
        stability_report(rows, repeats=3)


def test_retry_dedup_preserves_model_and_cap_identity() -> None:
    from trajjudge.judging import latest_rows
    original = row("a", 0, 1)
    other = {**original, "judge_model": "another", "score": 3}
    assert len(latest_rows([original, other])) == 2
