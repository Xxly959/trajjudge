"""Known-answer tests for the PREREG_v2 statistical fixes.

Every fixture here is synthetic and is not experiment evidence. Each test targets a
defect that was actually present in the v1 analysis path.
"""
from __future__ import annotations

import json

import pytest

from trajjudge import metrics as m
from trajjudge.analysis import cluster_interval, injection_report, stability_report
from trajjudge.robustness import (aggregation_diagnostics, draw_score, fisher_exact_two_sided,
                                  injection_sensitivity, missingness_report, missingness_sensitivity,
                                  mode_min, recover_draws)


def grade(trace, repeat, score, *, variant="original", grader="trajectory_accuracy",
          config=None, status="ok", defended=False, thinking=False):
    config = config or f"{grader}|think=off|direct1" + ("|def" if defended else "")
    return {"trace_id": trace, "repeat_id": repeat, "score": score, "variant": variant,
            "config": config, "grader": grader, "judge_model": "test", "thinking": thinking,
            "strategy": "direct", "max_tokens": 1024, "openjudge_commit": "c0", "status": status,
            "defended": defended, "usage": {"api_calls": 1, "cached_calls": 0,
                                           "prompt_tokens": 100, "completion_tokens": 10}}


class TestScenarioClusterBootstrap:
    """Translation copies are one independent unit, not two."""

    def test_copies_collapse_to_one_cluster(self):
        rows = [{"task_id": "T001zh_x", "category": "c", "human": True, "official": True,
                 "scores": {"trajectory_accuracy": 3}},
                {"task_id": "T001en_x", "category": "c", "human": True, "official": True,
                 "scores": {"trajectory_accuracy": 3}}]
        from trajjudge.analysis import agreement_with_clusters
        scenarios = {"T001zh_x": "x", "T001en_x": "x"}
        v1 = agreement_with_clusters(rows, resamples=40)
        v2 = agreement_with_clusters(rows, resamples=40, policy="v2", cluster_unit="scenario_id", scenarios=scenarios)
        assert v1["bootstrap_clusters"] == 2
        assert v2["bootstrap_clusters"] == 1
        assert v2["graders"]["trajectory_accuracy"]["bootstrap_clusters"] == 1

    def test_cluster_interval_keeps_within_cluster_records_together(self):
        items = [{"v": 1, "c": "a"}, {"v": 1, "c": "a"}, {"v": 0, "c": "b"}]
        seen = set()

        def stat(data):
            seen.add((sum(d["c"] == "a" for d in data), sum(d["c"] == "b" for d in data)))
            return sum(d["v"] for d in data) / len(data)

        cluster_interval(items, ["a", "a", "b"], stat, resamples=200)
        assert seen == {(0, 2), (2, 1), (4, 0)}
        assert all(a in (0, 2, 4) for a, _ in seen)

    def test_stability_uses_scenario_clusters(self):
        rows = [grade(t, r, 3) for t in ("zh", "en") for r in range(3)]
        entry = stability_report(rows, repeats=3, resamples=40, task_ids={"zh": "s", "en": "s"},
                                 policy="v2", cluster_unit="scenario_id")[0]
        assert entry["bootstrap_clusters"] == 1
        assert entry["summary"]["traces"] == 2


class TestFlipDenominator:
    """The denominator is distinct baseline-fail trajectories, not repeat observations."""

    def test_repeats_of_one_trace_are_one_trajectory(self):
        rows = [grade("a", r, 1) for r in range(3)]
        rows += [grade("a", r, 3, variant="L2/tool") for r in range(3)]
        entry = injection_report(rows, resamples=40, policy="v2")[0]
        assert entry["baseline_fail_observations"] == 3
        assert entry["baseline_fail_traces"] == 1 and entry["n_traj"] == 1
        assert entry["pairs"] == 3 and entry["n_scenario"] == 1
        assert entry["fail_to_pass_observations"] == 3

    def test_distinct_traces_count_separately(self):
        rows = [grade("a", 0, 1), grade("b", 0, 1),
                grade("a", 0, 3, variant="L2/tool"), grade("b", 0, 1, variant="L2/tool")]
        entry = injection_report(rows, resamples=40, policy="v2",
                                 task_ids={"a": "s1", "b": "s2"})[0]
        assert entry["n_traj"] == 2 and entry["n_scenario"] == 2 and entry["pairs"] == 2
        assert entry["case_study"] is True and entry["baseline_fail_flip_rate"] is None

    def test_rate_over_five_scenarios_uses_trajectory_denominator(self):
        rows = []
        for i in range(5):
            rows += [grade(f"t{i}", 0, 1), grade(f"t{i}", 0, 3 if i < 3 else 1, variant="L2/tool")]
        entry = injection_report(rows, resamples=40, policy="v2",
                                 task_ids={f"t{i}": f"s{i}" for i in range(5)})[0]
        assert entry["n_traj"] == 5 and entry["pairs"] == 5
        assert entry["baseline_fail_flip_rate"] == pytest.approx(0.6)
        assert entry["case_study"] is False

    def test_pass_to_fail_is_reported_not_only_inflation(self):
        rows = [grade("a", 0, 3), grade("a", 0, 1, variant="L2/tool")]
        entry = injection_report(rows, resamples=40, policy="v2")[0]
        assert entry["fail_to_pass_observations"] == 0
        assert entry["pass_to_fail_observations"] == 1
        assert entry["verdict_changed_observations"] == 1
        assert entry["asr"] == 0.0 and entry["verdict_flip_rate"] == 1.0

    def test_asr_and_verdict_flip_are_separate_metrics(self):
        rows = [grade("a", 0, 2.0, grader="trajectory_comprehensive"),
                grade("a", 0, 2.5, variant="L2/tool", grader="trajectory_comprehensive")]
        entry = injection_report(rows, resamples=40, policy="v2")[0]
        assert entry["asr"] == 1.0
        assert entry["verdict_flip_rate"] == 0.0


class TestCaseStudyGuard:
    """Fewer than five independent scenarios means no percentage conclusion."""

    @pytest.mark.parametrize("scenarios,expected", [(4, True), (5, False)])
    def test_threshold_is_five_scenarios(self, scenarios, expected):
        rows = []
        for i in range(scenarios):
            rows += [grade(f"t{i}", 0, 1), grade(f"t{i}", 0, 3, variant="L2/tool")]
        entry = injection_report(rows, resamples=40, policy="v2",
                                 task_ids={f"t{i}": f"s{i}" for i in range(scenarios)})[0]
        assert entry["case_study"] is expected
        assert entry["n_scenario"] == scenarios
        if expected:
            assert entry["baseline_fail_flip_rate"] is None
            assert entry["flip_ci"] is None and entry["flip_conclusion"] is None
            assert entry["flip_interval"]["status"] == "not_estimable"
        else:
            assert entry["baseline_fail_flip_rate"] == 1.0

    def test_v1_policy_still_reports_the_unguarded_rate(self):
        rows = [grade("a", 0, 1), grade("a", 0, 3, variant="L2/tool")]
        entry = injection_report(rows, resamples=40, policy="v1")[0]
        assert entry["baseline_fail_flip_rate"] == 1.0


class TestUndefinedBootstrapDraws:
    """Undefined draws are counted, and false precision is refused."""

    def test_all_undefined_is_not_estimable(self):
        out = m.bootstrap_interval(lambda idx: None, 4, resamples=50)
        assert out["status"] == "not_estimable" and out["ci"] is None
        assert out["undefined_draws"] == 50 and out["undefined_share"] == 1.0
        assert out["reason"] == m.NOT_ESTIMABLE

    def test_undefined_share_above_limit_is_unreliable(self):
        calls = {"n": 0}

        def stat(idx):
            calls["n"] += 1
            return None if calls["n"] % 5 == 0 else 0.5

        out = m.bootstrap_interval(stat, 4, resamples=100)
        assert out["undefined_share"] == pytest.approx(0.2)
        assert out["status"] == "unreliable" and out["ci"] is None

    def test_zero_width_interval_is_refused(self):
        out = m.bootstrap_interval(lambda idx: 1.0, 3, resamples=50)
        assert out["ci"] is None and out["status"] == "not_estimable"
        assert out["reason"] == m.NOT_ESTIMABLE

    def test_single_contributing_cluster_is_not_estimable(self):
        out = m.bootstrap_interval(lambda idx: len(idx) / 10, 1, resamples=50, contributing_clusters=1)
        assert out["status"] == "not_estimable" and out["ci"] is None

    def test_v1_primitive_still_drops_undefined_draws(self):
        assert m.bootstrap_ci(lambda idx: None, 4, resamples=50) is None
        assert m.bootstrap_ci(lambda idx: 1.0, 3, resamples=50) == (1.0, 1.0)


class TestSharedDrawAggregation:
    """Voting reuses average's draws and degenerates to min under the MIN tie-break."""

    def test_draw_score_matches_upstream_formula(self):
        assert draw_score("trajectory_accuracy", json.dumps({"score": 2})) == 2.0
        steps = [{"contribution_score": 4, "relevance_score": 4, "accuracy_score": 4,
                  "efficiency_score": 4, "step_index": i, "step_reason": "r"} for i in range(2)]
        assert draw_score("trajectory_comprehensive", json.dumps({"step_evaluations": steps})) == 0.75

    def test_operation_order_changes_floats_and_therefore_the_mode(self):
        def steps(totals):
            n = 3
            return [{"contribution_score": totals[0] // n + (i < totals[0] % n),
                     "relevance_score": totals[1] // n + (i < totals[1] % n),
                     "accuracy_score": totals[2] // n + (i < totals[2] % n),
                     "efficiency_score": totals[3] // n + (i < totals[3] % n),
                     "step_index": i, "step_reason": "r"} for i in range(n)]

        a = draw_score("trajectory_comprehensive", json.dumps({"step_evaluations": steps([11, 12, 15, 11])}))
        b = draw_score("trajectory_comprehensive", json.dumps({"step_evaluations": steps([12, 12, 14, 11])}))
        assert a == pytest.approx(b, abs=1e-12) and a != b
        assert mode_min([a, 0.75, b]) == 0.75

    def test_mode_min_resolves_ties_to_minimum(self):
        assert mode_min([3, 3, 1]) == 3
        assert mode_min([3, 2, 1]) == 1
        assert mode_min([0.5, 0.5, 0.9]) == 0.5

    def _entries(self, draws, *, prompt=100, completion=10, model="test"):
        out = []
        for i, score in enumerate(draws):
            raw = {"score": score}
            out.append({"tag": f"p3/t/original/trajectory_accuracy|think=off|{'direct1' if i == 0 else 'average3'}/0",
                        "model": model, "thinking": False, "prompt_tokens": prompt,
                        "completion_tokens": completion, "text": json.dumps(raw)})
        return out

    def _rows(self, draws, *, voting=None, prompt=300, completion=30):
        avg = grade("t", 0, sum(draws) / len(draws), config="trajectory_accuracy|think=off|average3")
        avg["strategy"] = "average"
        avg["usage"] = {"api_calls": 2, "cached_calls": 1, "prompt_tokens": prompt, "completion_tokens": completion}
        rows = [avg]
        if voting is not None:
            v = grade("t", 0, voting, config="trajectory_accuracy|think=off|voting3")
            v["strategy"] = "voting"
            v["usage"] = {"api_calls": 0, "cached_calls": 3, "prompt_tokens": prompt, "completion_tokens": completion}
            rows.append(v)
        return rows

    def test_recovery_requires_token_identity(self):
        rows = self._rows([3, 3, 1], voting=3)
        entries = self._entries([3, 3, 1], prompt=99)
        out = recover_draws(rows, entries)
        assert out["panels"] == []
        assert "token totals" in out["excluded"][0]["reason"]

    def test_recovery_requires_reproducing_the_recorded_average(self):
        rows = self._rows([3, 3, 1], voting=3)
        entries = self._entries([3, 3, 3])
        out = recover_draws(rows, entries)
        assert out["panels"] == []
        assert "recorded average" in out["excluded"][0]["reason"]

    def test_recovery_requires_reproducing_the_recorded_voting(self):
        rows = self._rows([3, 2, 1], voting=3)
        out = recover_draws(rows, self._entries([3, 2, 1]))
        assert out["panels"] == []
        assert "recorded voting" in out["excluded"][0]["reason"]

    def test_verified_panel_reports_shares_and_draw_sharing(self):
        rows = self._rows([3, 2, 1], voting=1)
        out = aggregation_diagnostics(rows, self._entries([3, 2, 1]))
        assert out["draw_level"]["panels"] == 1
        assert out["draw_level"]["all_draws_distinct"] == 1
        assert out["draw_level"]["voting_eq_min"] == 1
        assert out["draw_level"]["voting_lt_average"] == 1
        assert out["row_level"]["shared_token_panels"] == 1
        assert out["row_level"]["voting_zero_new_calls"] == 1
        assert out["recovery"]["coverage"] == 1.0

    def test_unrecoverable_panels_are_listed_not_dropped_silently(self):
        rows = self._rows([3, 3, 1], voting=3)
        out = aggregation_diagnostics(rows, self._entries([3, 3, 1])[:2])
        assert out["draw_level"]["panels"] == 0
        assert out["recovery"]["excluded"][0]["reason"].startswith("expected 3 cached draws")
        assert out["row_level"]["ok_average_voting_pairs"] == 1


class TestMissingnessSensitivity:
    """Invalid grades are neither random nor silently imputed."""

    def test_stratum_specific_invalidity_is_visible(self):
        rows = [grade("a", 0, 3, grader="trajectory_accuracy"),
                grade("b", 0, None, grader="trajectory_comprehensive", status="error"),
                grade("c", 0, 0.5, grader="trajectory_comprehensive")]
        out = missingness_report(rows)
        assert out["invalid"] == 1 and out["invalid_rate"] == pytest.approx(1 / 3)
        by_grader = {b["value"]: b for b in out["strata"]["grader"]}
        assert by_grader["trajectory_accuracy"]["invalid"] == 0
        assert by_grader["trajectory_comprehensive"]["invalid"] == 1

    def test_defended_arm_failure_rate_is_tested(self):
        rows = ([grade(f"d{i}", 0, None, status="error", defended=True) for i in range(4)]
                + [grade(f"u{i}", 0, 3) for i in range(6)])
        out = missingness_report(rows)
        assert out["defended_vs_invalid"]["table"] == [[4, 0], [0, 6]]
        assert out["defended_vs_invalid"]["fisher_exact_p"] == pytest.approx(0.0047619047619, abs=1e-9)
        assert out["defended_vs_invalid"]["status"] == "exploratory"

    def test_fisher_exact_known_values(self):
        assert fisher_exact_two_sided(1, 9, 11, 3) == pytest.approx(0.0027594561, abs=1e-9)
        assert fisher_exact_two_sided(0, 0, 0, 0) == 1.0
        assert fisher_exact_two_sided(5, 5, 5, 5) == pytest.approx(1.0)

    def test_agreement_arms_coincide_when_nothing_is_missing(self):
        joined = [{"human": True, "scores": {"trajectory_accuracy": 3}},
                  {"human": False, "scores": {"trajectory_accuracy": 1}}]
        out = missingness_sensitivity(joined, "trajectory_accuracy", 2.0)
        assert out["informative"] is False
        assert out["arms"]["observed"]["accuracy"] == 1.0
        assert out["arms"]["invalid_as_pass"] == out["arms"]["observed"]

    def test_agreement_arms_bound_a_missing_grade(self):
        joined = [{"human": False, "scores": {"trajectory_accuracy": 3}},
                  {"human": False, "scores": {}}]
        out = missingness_sensitivity(joined, "trajectory_accuracy", 2.0)
        assert out["informative"] is True
        assert out["arms"]["observed"]["n"] == 1
        assert out["arms"]["invalid_as_pass"]["confusion"]["fp"] == 2
        assert out["arms"]["invalid_as_fail"]["confusion"]["tn"] == 1

    def test_injection_observed_arm_excludes_invalid_pairs(self):
        rows = [grade("a", 0, 0.5, grader="trajectory_comprehensive"),
                grade("a", 0, None, variant="L2/tool", grader="trajectory_comprehensive", status="error")]
        out = injection_sensitivity(rows, "trajectory_comprehensive", 0.6)
        assert out["arms"]["observed"]["pairs"] == 0
        assert out["arms"]["observed"]["excluded"] == 1
        assert out["arms"]["invalid_as_pass"]["pairs"] == 1
        assert out["arms"]["invalid_as_fail"]["pairs"] == 1

    def test_defense_gap_survives_both_imputation_arms(self):
        rows = []
        for defended in (False, True):
            base = 0.5
            perturbed = 0.9 if not defended else 0.5
            rows.append(grade("a", 0, base, grader="trajectory_comprehensive", defended=defended))
            rows.append(grade("a", 0, perturbed, variant="L2/tool",
                              grader="trajectory_comprehensive", defended=defended))
            rows.append(grade("b", 0, None, grader="trajectory_comprehensive",
                              defended=defended, status="error"))
            rows.append(grade("b", 0, None, variant="L2/tool", grader="trajectory_comprehensive",
                              defended=defended, status="error"))
        gaps = []
        for arm in ("observed", "invalid_as_pass", "invalid_as_fail"):
            undef = injection_sensitivity([r for r in rows if not r["defended"]],
                                          "trajectory_comprehensive", 0.6)["arms"][arm]["asr"]
            defended = injection_sensitivity([r for r in rows if r["defended"]],
                                             "trajectory_comprehensive", 0.6)["arms"][arm]["asr"]
            gaps.append(undef - defended)
        assert all(g > 0.4 for g in gaps)