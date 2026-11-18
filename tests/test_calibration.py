"""Phase 4 calibration tests: the failures that would silently inflate a result."""
from __future__ import annotations

import math

import pytest

from trajjudge import calibration as cal
from trajjudge.agreement import THRESHOLDS

ACC = "trajectory_accuracy"
COMP = "trajectory_comprehensive"


def row(trace, scenario, human, score, *, official=True, comp=None, task=None):
    return {"trace_id": trace, "task_id": task or scenario, "scenario_id": scenario,
            "human": human, "official": official,
            "scores": {ACC: score, COMP: comp if comp is not None else score}}


def clusters(*rows):
    return {r["trace_id"]: r["scenario_id"] for r in rows}


def oof_row(trace, scenario, human, score, pred, *, fallback=False):
    return {"trace_id": trace, "task_id": scenario, "scenario_id": scenario, "human": human,
            "official": True, "score": score, "pred": pred, "threshold": "threshold:2.0",
            "fallback": fallback}


class TestFrozenGrid:
    def test_accuracy_grid_is_the_prereg_list(self):
        assert cal.GRIDS[ACC] == (1.0, 1.5, 2.0, 2.5, 3.0)

    def test_comprehensive_grid_is_regular_not_quantiles(self):
        assert cal.GRIDS[COMP] == tuple(round(0.50 + 0.05 * i, 2) for i in range(11))
        assert len(cal.GRIDS[COMP]) == 11

    def test_sentinels_are_offered_but_have_no_distance_to_default(self):
        pool = cal.candidates(ACC)
        assert [c["kind"] for c in pool[-2:]] == ["always_pass", "always_fail"]
        assert all(c["distance"] == math.inf for c in pool[-2:])

    def test_unknown_grader_is_refused_not_defaulted(self):
        with pytest.raises(ValueError):
            cal.candidates("trajectory_vibes")

    def test_sentinel_predictions_ignore_the_score(self):
        assert cal.predict(1.0, {"kind": "always_pass", "value": None}) is True
        assert cal.predict(3.0, {"kind": "always_fail", "value": None}) is False
        assert cal.predict(2.0, {"kind": "threshold", "value": 2.0}) is True
        assert cal.predict(1.9, {"kind": "threshold", "value": 2.0}) is False


class TestSelection:
    def test_tie_goes_to_the_upstream_default(self):
        # On integer scores 1.5 and 2.0 decide identically; the default must win.
        train = [row("a", "s1", True, 3.0), row("b", "s2", False, 1.0)]
        chosen = cal.select(train, ACC)
        assert chosen["threshold"] == "threshold:2.0"

    def test_equal_distance_tie_goes_to_the_smaller_value(self, monkeypatch):
        # A symmetric grid around the default makes the two distances equal, so
        # only the second tie-break clause can decide.
        monkeypatch.setitem(cal.GRIDS, COMP, (0.5, 0.7))
        train = [row("a", "s1", True, 0.9), row("b", "s2", False, 0.4)]
        chosen = cal.select(train, COMP)
        assert chosen["train_metrics"]["balanced_accuracy"] == 1.0
        assert chosen["choice"]["value"] == 0.5

    def test_sentinel_loses_a_tie_to_a_real_threshold(self):
        train = [row("a", "s1", True, 3.0), row("b", "s2", False, 1.0)]
        chosen = cal.select(train, ACC)
        assert chosen["choice"]["kind"] == "threshold"

    def test_sentinel_wins_when_no_threshold_meets_the_miss_target(self):
        train = [row("a", "s1", False, 3.0), row("b", "s2", True, 3.0)]
        chosen = cal.select(train, ACC, target_miss=0.10)
        assert chosen["threshold"] == "always_fail"
        assert chosen["train_metrics"]["miss_rate"] == 0.0

    def test_missing_class_is_undefined_not_a_perfect_score(self):
        train = [row("a", "s1", True, 3.0), row("b", "s2", True, 2.0)]
        chosen = cal.select(train, ACC)
        assert chosen["undefined"] is True
        assert chosen["choice"] is None
        assert "未定义" in chosen["reason"]

    def test_every_candidate_is_reported_so_the_choice_is_auditable(self):
        train = [row("a", "s1", True, 3.0), row("b", "s2", False, 1.0)]
        chosen = cal.select(train, ACC)
        assert len(chosen["considered"]) == len(cal.GRIDS[ACC]) + 2

    def test_miss_rate_target_picks_closest_from_below(self):
        # Four human fails at 1,2,2,3 and four human passes at 3.
        train = [row(f"f{i}", "s1", False, s) for i, s in enumerate((1.0, 2.0, 2.0, 3.0))]
        train += [row(f"p{i}", "s2", True, 3.0) for i in range(4)]
        chosen = cal.select(train, ACC, target_miss=0.25)
        assert chosen["undefined"] is False
        assert chosen["train_metrics"]["miss_rate"] <= 0.25 + 1e-12

    def test_miss_rate_never_exceeds_the_target(self):
        train = [row("a", "s1", False, 1.0), row("b", "s2", True, 3.0)]
        for target in cal.MISS_RATES:
            chosen = cal.select(train, ACC, target_miss=target)
            if not chosen["undefined"]:
                assert chosen["train_metrics"]["miss_rate"] <= target + 1e-12

    def test_always_fail_makes_every_nonnegative_target_feasible(self):
        train = [row("a", "s1", False, 3.0), row("b", "s2", True, 3.0)]
        chosen = cal.select(train, ACC, target_miss=0.0)
        assert chosen["undefined"] is False
        assert chosen["threshold"] == "always_fail"

    def test_infeasible_miss_rate_is_undefined(self):
        train = [row("a", "s1", False, 3.0), row("b", "s2", True, 3.0)]
        chosen = cal.select(train, ACC, target_miss=-0.01)
        assert chosen["undefined"] is True
        assert chosen["choice"] is None


class TestFolds:
    def test_each_scenario_is_held_out_exactly_once(self):
        rows = [row("a", "s1", True, 3.0), row("b", "s2", False, 1.0), row("c", "s3", True, 2.0)]
        plan = cal.fold_plan(rows, clusters(*rows))
        assert [f["scenario_id"] for f in plan] == ["s1", "s2", "s3"]
        assert all(len(f["test"]) == 1 for f in plan)

    def test_translation_twins_are_never_split_across_train_and_test(self):
        rows = [row("zh", "s1", True, 3.0, task="T_zh"), row("en", "s1", False, 1.0, task="T_en"),
                row("other", "s2", True, 2.0)]
        plan = cal.fold_plan(rows, clusters(*rows))
        fold = next(f for f in plan if f["scenario_id"] == "s1")
        assert {r["trace_id"] for r in fold["test"]} == {"zh", "en"}
        assert {r["trace_id"] for r in fold["train"]} == {"other"}

    def test_held_out_labels_cannot_change_the_threshold(self):
        # s3 holds a human fail scoring 2.0. Training on s1+s2 alone picks 2.0 and
        # therefore mispredicts it; leaking s3 into training would pick 2.5 and
        # look perfect. The wrong prediction is the evidence of no leakage.
        rows = [row("a", "s1", True, 3.0), row("b", "s2", False, 1.0), row("c", "s3", False, 2.0)]
        result = cal.out_of_fold(cal.fold_plan(rows, clusters(*rows)), ACC)
        fold = next(f for f in result["folds"] if f["scenario_id"] == "s3")
        assert fold["threshold"] == "threshold:2.0"
        held = next(r for r in result["oof"] if r["trace_id"] == "c")
        assert held["pred"] is True and held["human"] is False

    def test_undefined_fold_falls_back_loudly_and_is_counted(self):
        rows = [row("a", "s1", True, 3.0), row("b", "s2", True, 2.0)]
        result = cal.out_of_fold(cal.fold_plan(rows, clusters(*rows)), ACC)
        assert result["undefined_folds"] == 2
        assert result["undefined_share"] == 1.0
        assert all(f["fallback"] for f in result["folds"])
        assert all(f["threshold"] == f"threshold:{THRESHOLDS[ACC]}" for f in result["folds"])
        assert len(result["oof"]) == 2

    def test_missing_score_is_dropped_from_oof_not_imputed(self):
        rows = [row("a", "s1", True, 3.0), row("b", "s2", False, 1.0)]
        rows[1]["scores"][ACC] = None
        result = cal.out_of_fold(cal.fold_plan(rows, clusters(*rows)), ACC)
        assert [r["trace_id"] for r in result["oof"]] == ["a"]

    def test_unmapped_trace_is_loud(self):
        rows = [row("a", "s1", True, 3.0)]
        with pytest.raises(KeyError):
            cal.fold_plan(rows, {})


class TestBinaryMetrics:
    def test_empty_class_is_none_not_zero(self):
        stats = cal.binary_metrics([True, True], [True, False])
        assert stats["specificity"] is None
        assert stats["miss_rate"] is None
        assert stats["balanced_accuracy"] is None
        assert stats["sensitivity"] == 0.5

    def test_miss_rate_counts_human_fails_judged_pass(self):
        stats = cal.binary_metrics([False, False, True, True], [True, False, True, True])
        assert stats["miss_rate"] == 0.5
        assert stats["specificity"] == 0.5

    def test_perfect_separation(self):
        stats = cal.binary_metrics([True, False], [True, False])
        assert stats["balanced_accuracy"] == 1.0
        assert stats["miss_rate"] == 0.0


class TestAveragePrecision:
    def test_hand_computed_step_interpolation(self):
        labels = [True, False, True, False]
        scores = [0.9, 0.8, 0.7, 0.6]
        assert cal.average_precision(labels, scores) == pytest.approx(5 / 6)

    def test_ties_are_grouped_not_ordered_arbitrarily(self):
        assert cal.average_precision([True, False, False], [1.0, 1.0, 0.0]) == pytest.approx(0.5)

    def test_single_class_is_none(self):
        assert cal.average_precision([True, True], [0.9, 0.1]) is None
        assert cal.average_precision([False, False], [0.9, 0.1]) is None

    def test_length_mismatch_is_refused(self):
        with pytest.raises(ValueError):
            cal.average_precision([True], [0.1, 0.2])

    def test_perfect_ranking_is_one(self):
        assert cal.average_precision([True, True, False], [0.9, 0.8, 0.1]) == pytest.approx(1.0)


class TestSummarize:
    @staticmethod
    def mixed(n_scenario, inverted=()):
        """One pass and one fail per scenario; ``inverted`` scenarios rank backwards."""
        rows = []
        for k in range(n_scenario):
            for human in (True, False):
                good = (k not in inverted) == human
                rows.append(oof_row(f"t{k}{int(human)}", f"s{k}", human, 3.0 if good else 1.0, human))
        return rows

    def test_auc_ci_covering_half_flags_no_discrimination(self):
        # Half the scenarios rank pass above fail, half below: AUC is exactly 0.5
        # but resampling the clusters moves it, so the interval is estimable.
        rows = self.mixed(6, inverted=(1, 3, 5))
        out = cal.summarize(rows, resamples=400)
        assert out["auc_pass"] == pytest.approx(0.5)
        assert out["intervals"]["auc_pass"]["ci"] is not None
        assert out["auc_covers_half"] is True
        assert out["no_usable_discrimination"] is True

    def test_separated_scores_do_not_flag(self):
        out = cal.summarize(self.mixed(10, inverted=(9,)), resamples=400)
        assert out["auc_pass"] == pytest.approx(0.9)
        assert out["intervals"]["auc_pass"]["ci"] is not None
        assert out["no_usable_discrimination"] is False

    def test_not_estimable_auc_is_not_reported_as_usable(self):
        rows = [oof_row(f"t{i}", f"s{i}", True, 2.0, True) for i in range(6)]
        out = cal.summarize(rows, resamples=50)
        assert out["auc_pass"] is None
        assert out["auc_covers_half"] is None
        assert out["no_usable_discrimination"] is False

    def test_constant_prediction_refuses_a_zero_width_interval(self):
        rows = [oof_row(f"t{i}", f"s{i}", True, 2.0, True) for i in range(6)]
        out = cal.summarize(rows, resamples=200)
        assert out["accuracy"] == 1.0
        assert out["intervals"]["accuracy"]["ci"] is None
        assert out["intervals"]["accuracy"]["status"] == "not_estimable"

    def test_few_scenarios_are_a_case_study(self):
        assert cal.summarize(self.mixed(3), resamples=50)["case_study"] is True

    def test_five_scenarios_are_not_a_case_study(self):
        assert cal.summarize(self.mixed(5), resamples=50)["case_study"] is False

    def test_fallback_rows_are_counted_not_hidden(self):
        rows = self.mixed(6)
        for r in rows[:3]:
            r["fallback"] = True
        assert cal.summarize(rows, resamples=50)["fallback_rows"] == 3

    def test_empty_frame_is_not_estimable(self):
        assert cal.summarize([], resamples=50)["status"] == "not_estimable"

    def test_baselines_are_reported_alongside(self):
        out = cal.summarize(self.mixed(6), resamples=50)
        assert set(out["baselines"]) == {"always_pass", "majority", "random"}
        assert out["baseline_balanced"]["always_pass"] == 0.5

    def test_intervals_do_not_depend_on_input_row_order(self):
        rows = self.mixed(6, inverted=(1, 3, 5))
        forward = cal.summarize(rows, resamples=200)
        backward = cal.summarize(list(reversed(rows)), resamples=200)
        assert forward["intervals"] == backward["intervals"]


class TestHardSamples:
    def test_requires_all_four_conditions(self):
        good = row("a", "s1", False, 3.0, comp=0.9)
        assert [r["trace_id"] for r in cal.hard_samples([good])] == ["a"]

    def test_human_pass_is_excluded(self):
        assert cal.hard_samples([row("a", "s1", True, 3.0, comp=0.9)]) == []

    def test_framework_fail_is_excluded(self):
        assert cal.hard_samples([row("a", "s1", False, 3.0, comp=0.9, official=False)]) == []

    def test_either_grader_below_threshold_is_excluded(self):
        assert cal.hard_samples([row("a", "s1", False, 1.0, comp=0.9)]) == []
        assert cal.hard_samples([row("a", "s1", False, 3.0, comp=0.5)]) == []

    def test_missing_score_is_excluded_not_treated_as_pass(self):
        r = row("a", "s1", False, 3.0, comp=0.9)
        r["scores"][COMP] = None
        assert cal.hard_samples([r]) == []


class TestHybridEvidence:
    def test_the_four_groups_partition_the_human_fails(self):
        rows = [row("a", "s1", False, 3.0, comp=0.9, official=False),   # framework only
                row("b", "s2", False, 1.0, comp=0.9, official=True),    # graders only
                row("c", "s3", False, 3.0, comp=0.9, official=True),    # neither
                row("d", "s4", False, 1.0, comp=0.9, official=False),   # both
                row("e", "s5", True, 3.0, comp=0.9, official=True)]
        ev = cal.hybrid_evidence(rows)
        groups = [ev["framework_only"], ev["graders_only"], ev["neither"], ev["both"]]
        assert sum(len(g) for g in groups) == ev["n_human_fail"] == 4
        assert ev["framework_only"] == ["a"]
        assert ev["graders_only"] == ["b"]
        assert ev["neither"] == ["c"]
        assert ev["both"] == ["d"]

    def test_union_miss_rate_is_never_worse_than_either_alone(self):
        rows = [row("a", "s1", False, 3.0, comp=0.9, official=False),
                row("b", "s2", False, 1.0, comp=0.9, official=True),
                row("c", "s3", True, 3.0, comp=0.9)]
        ev = cal.hybrid_evidence(rows)
        assert ev["miss_rate_union"] <= min(ev["miss_rate"].values())

    def test_no_human_fail_gives_none_not_zero(self):
        ev = cal.hybrid_evidence([row("a", "s1", True, 3.0, comp=0.9)])
        assert ev["n_human_fail"] == 0
        assert ev["miss_rate_union"] is None
        assert all(v is None for v in ev["miss_rate"].values())

    def test_scenario_count_uses_the_cluster_not_the_task(self):
        rows = [row("zh", "s1", False, 1.0, comp=0.9, task="T_zh"),
                row("en", "s1", False, 1.0, comp=0.9, task="T_en")]
        assert cal.hybrid_evidence(rows)["n_scenario_fail"] == 1

    def test_false_kill_counts_disagreement_not_agreement(self):
        # The framework passing every human pass is agreement, so it must count 0
        # false kills; counting it as 32 would invert the hybrid-scoring verdict.
        rows = [row("p1", "s1", True, 3.0, comp=0.9, official=True),
                row("p2", "s2", True, 1.0, comp=0.9, official=True),
                row("f1", "s3", False, 3.0, comp=0.9, official=True)]
        ev = cal.hybrid_evidence(rows)
        assert ev["framework_false_fail_on_human_pass"] == 0
        assert ev["grader_false_fail_on_human_pass"][ACC] == 1
        assert ev["grader_false_fail_on_human_pass"][COMP] == 0

    def test_framework_false_kill_is_a_human_pass_it_failed(self):
        rows = [row("p1", "s1", True, 3.0, comp=0.9, official=False),
                row("p2", "s2", True, 3.0, comp=0.9, official=True)]
        assert cal.hybrid_evidence(rows)["framework_false_fail_on_human_pass"] == 1

    def test_missing_grade_is_neither_a_catch_nor_a_kill(self):
        caught = row("f1", "s1", False, 3.0, comp=0.9)
        killed = row("p1", "s2", True, 3.0, comp=0.9)
        for r in (caught, killed):
            r["scores"][ACC] = None
        ev = cal.hybrid_evidence([caught, killed])
        assert ev["caught_by"][ACC] == 0
        assert ev["grader_false_fail_on_human_pass"][ACC] == 0