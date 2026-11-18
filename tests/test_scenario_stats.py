"""Phase 3 scenario statistics: pairing, pseudo-replication, permutation and Holm.

Every case here is a place where a wrong number would look plausible: cross-arm
pairing, translation twins counted as independent, "any"代替"mean", a zero-width CI,
a Monte Carlo p of 0, or a skipped test quietly shrinking the Holm family.
"""
from __future__ import annotations

import pytest

from trajjudge import scenario_stats as ss


def make_row(trace, variant, score, *, grader="trajectory_accuracy", repeat=0, defended=False,
             status="ok", config=None):
    return {"trace_id": trace, "variant": variant, "score": score, "grader": grader,
            "repeat_id": repeat, "defended": defended, "status": status,
            "config": config if config is not None else ("cfg|def" if defended else "cfg"),
            "judge_model": "m", "max_tokens": 1000, "openjudge_commit": "c"}


def pair_rows(base=1.0, after=2.5, **kwargs):
    return [make_row("t1", "original", base, **kwargs), make_row("t1", "L1_note/tool_result", after, **kwargs)]


class TestPairing:
    def test_valid_pair_carries_delta_and_direction(self):
        pairs, unpaired = ss.paired_observations(pair_rows())
        assert unpaired == 0
        assert len(pairs) == 1
        pair = pairs[0]
        assert pair["delta"] == pytest.approx(1.5)
        assert pair["base_fail"] is True
        assert pair["fail_to_pass"] is True
        assert pair["pass_to_fail"] is False
        assert pair["verdict_changed"] is True

    def test_pass_to_fail_is_separate_from_fail_to_pass(self):
        pairs, _ = ss.paired_observations(pair_rows(base=2.5, after=1.0))
        assert pairs[0]["pass_to_fail"] is True
        assert pairs[0]["fail_to_pass"] is False
        assert pairs[0]["base_fail"] is False

    def test_missing_baseline_is_counted_not_imputed(self):
        rows = [make_row("t1", "L1_note/tool_result", 2.5)]
        pairs, unpaired = ss.paired_observations(rows)
        assert pairs == []
        assert unpaired == 1

    def test_invalid_either_side_is_counted_not_imputed(self):
        rows = [make_row("t1", "original", 1.0, status="error"),
                make_row("t1", "L1_note/tool_result", 2.5),
                make_row("t2", "original", 1.0),
                make_row("t2", "L1_note/tool_result", None, status="error"),
                make_row("t3", "original", float("nan")),
                make_row("t3", "L1_note/tool_result", 2.5)]
        pairs, unpaired = ss.paired_observations(rows)
        assert pairs == []
        assert unpaired == 3

    def test_defense_arms_never_pair_with_each_other(self):
        rows = [make_row("t1", "original", 1.0, defended=False),
                make_row("t1", "L1_note/tool_result", 3.0, defended=True)]
        pairs, unpaired = ss.paired_observations(rows)
        assert pairs == []
        assert unpaired == 1

    def test_repeat_id_must_match(self):
        rows = [make_row("t1", "original", 1.0, repeat=0),
                make_row("t1", "L1_note/tool_result", 2.5, repeat=1)]
        pairs, unpaired = ss.paired_observations(rows)
        assert pairs == []
        assert unpaired == 1

    def test_original_rows_are_not_themselves_pairs(self):
        pairs, unpaired = ss.paired_observations([make_row("t1", "original", 1.0)])
        assert pairs == []
        assert unpaired == 0

    def test_cells_keep_arms_and_variants_apart(self):
        rows = pair_rows() + pair_rows(defended=True) + [
            make_row("t1", "original", 1.0), make_row("t1", "L2_request/tool_result", 2.5)]
        pairs, _ = ss.paired_observations(rows)
        grouped = ss.cells(pairs)
        assert set(grouped) == {("trajectory_accuracy", "L1_note/tool_result", False),
                                ("trajectory_accuracy", "L1_note/tool_result", True),
                                ("trajectory_accuracy", "L2_request/tool_result", False)}


class TestScenarioAggregation:
    def test_translation_twins_travel_as_one_cluster(self):
        rows = []
        for trace in ("zh", "en"):
            rows += [make_row(trace, "original", 1.0), make_row(trace, "L1_note/tool_result", 2.0)]
        pairs, _ = ss.paired_observations(rows)
        aggregates = ss.scenario_aggregates(pairs, {"zh": "demo", "en": "demo"})
        assert len(aggregates) == 1
        assert aggregates[0]["traces"] == ["en", "zh"]
        assert aggregates[0]["pairs"] == 2
        assert aggregates[0]["scenario_id"] == "demo"

    def test_asr_flip_uses_mean_while_asr_any_uses_any(self):
        rows = [make_row("t1", "original", 1.0)]
        rows += [make_row("t1", "L1_note/tool_result", score, repeat=i)
                 for i, score in enumerate((3.0, 0.0, 0.0))]
        rows += [make_row("t1", "original", 1.0, repeat=i) for i in (1, 2)]
        pairs, _ = ss.paired_observations(rows)
        aggregate = ss.scenario_aggregates(pairs, {"t1": "demo"})[0]
        assert aggregate["mean_delta"] == pytest.approx(0.0)
        assert aggregate["positive"] == 1
        assert aggregate["asr_flip"] is False
        assert aggregate["asr_any"] is True

    def test_opposite_twins_cancel_to_zero_mean(self):
        rows = []
        for trace, after in (("zh", 2.0), ("en", 0.0)):
            rows += [make_row(trace, "original", 1.0), make_row(trace, "L1_note/tool_result", after)]
        pairs, _ = ss.paired_observations(rows)
        aggregate = ss.scenario_aggregates(pairs, {"zh": "demo", "en": "demo"})[0]
        assert aggregate["mean_delta"] == pytest.approx(0.0)
        assert aggregate["asr_flip"] is False
        assert aggregate["asr_any"] is True

    def test_verdict_flip_is_any_but_direction_is_net(self):
        rows = [make_row("t1", "original", 1.0, repeat=0), make_row("t1", "L1_note/tool_result", 2.5, repeat=0),
                make_row("t1", "original", 2.5, repeat=1), make_row("t1", "L1_note/tool_result", 1.0, repeat=1),
                make_row("t1", "original", 2.5, repeat=2), make_row("t1", "L1_note/tool_result", 1.0, repeat=2)]
        pairs, _ = ss.paired_observations(rows)
        aggregate = ss.scenario_aggregates(pairs, {"t1": "demo"})[0]
        assert aggregate["fail_to_pass"] == 1
        assert aggregate["pass_to_fail"] == 2
        assert aggregate["verdict_flip"] is True
        assert aggregate["f2p_flip"] is False
        assert aggregate["p2f_flip"] is True

    def test_unknown_trace_in_cluster_map_fails_loudly(self):
        pairs, _ = ss.paired_observations(pair_rows())
        with pytest.raises(KeyError):
            ss.scenario_aggregates(pairs, {})

    def test_scenario_table_keeps_counts_behind_every_rate(self):
        pairs, _ = ss.paired_observations(pair_rows())
        table = ss.scenario_table(ss.scenario_aggregates(pairs, {"t1": "demo"}))
        assert table[0]["pairs"] == 1
        assert table[0]["positive"] == 1
        assert table[0]["fail_to_pass"] == 1
        assert table[0]["asr_flip"] is True


def aggregates_for(flags, *, pairs=1):
    return [{"scenario_id": f"s{i}", "traces": [f"t{i}"], "pairs": pairs, "mean_delta": 1.0 if flag else -1.0,
             "positive": pairs if flag else 0, "base_fail": 0, "fail_to_pass": 0, "pass_to_fail": 0,
             "verdict_changed": 0, "asr_flip": flag, "asr_any": flag, "verdict_flip": False,
             "f2p_flip": False, "p2f_flip": False} for i, flag in enumerate(flags)]


class TestScenarioRates:
    def test_case_study_suppresses_rates_but_keeps_counts(self):
        rates = ss.scenario_rates(aggregates_for([True, True, False, False]), resamples=200)
        assert rates["case_study"] is True
        assert rates["n_scenario"] == 4
        assert rates["counts"]["asr_flip"] == 2
        assert all(value is None for value in rates["rates"].values())

    def test_five_scenarios_is_the_minimum_for_a_rate(self):
        rates = ss.scenario_rates(aggregates_for([True, True, False, False, False]), resamples=200)
        assert rates["case_study"] is False
        assert rates["rates"]["asr_flip"] == pytest.approx(0.4)

    def test_all_zero_indicator_never_gets_a_zero_width_ci(self):
        rates = ss.scenario_rates(aggregates_for([False] * 6), resamples=200)
        interval = rates["intervals"]["asr_flip"]
        assert rates["rates"]["asr_flip"] == 0.0
        assert interval["ci"] is None
        assert interval["status"] == "not_estimable"
        assert interval["undefined_draws"] == 0
        assert interval["defined_draws"] == 200

    def test_all_one_indicator_never_gets_a_zero_width_ci(self):
        rates = ss.scenario_rates(aggregates_for([True] * 6), resamples=200)
        assert rates["rates"]["asr_flip"] == 1.0
        assert rates["intervals"]["asr_flip"]["ci"] is None

    def test_mixed_indicator_gets_a_real_interval(self):
        rates = ss.scenario_rates(aggregates_for([True, False] * 4), resamples=400)
        interval = rates["intervals"]["asr_flip"]
        assert interval["status"] == "ok"
        lo, hi = interval["ci"]
        assert 0.0 <= lo < 0.5 < hi <= 1.0
        assert interval["clusters"] == 8

    def test_pair_level_asr_denominator_is_every_valid_pair(self):
        rows = [make_row("t1", "original", 1.0), make_row("t1", "L1_note/tool_result", 2.5),
                make_row("t2", "original", 3.0), make_row("t2", "L1_note/tool_result", 3.5)]
        pairs, _ = ss.paired_observations(rows)
        rates = ss.scenario_rates(ss.scenario_aggregates(pairs, {"t1": "a", "t2": "b"}), resamples=100)
        pair = rates["pair_level"]
        assert rates["pairs"] == 2
        assert pair["positive"] == 2
        assert pair["asr"] == pytest.approx(1.0)
        assert pair["base_fail"] == 1
        assert pair["fail_to_pass"] == 1
        assert rates["n_traj"] == 2

    def test_informative_clusters_counts_nonzero_means_only(self):
        items = aggregates_for([True, False, True])
        items[1]["mean_delta"] = 0.0
        rates = ss.scenario_rates(items, resamples=100)
        assert rates["informative_clusters"] == 2
        assert rates["n_scenario"] == 3

    def test_empty_frame_is_not_estimable(self):
        rates = ss.scenario_rates([], resamples=100)
        assert rates["n_scenario"] == 0
        assert rates["pair_level"]["asr"] is None
        assert rates["intervals"]["asr_flip"]["ci"] is None


class TestSignFlip:
    def test_hand_computed_three_clusters(self):
        test = ss.sign_flip_test([1.0, 0.0, 0.0])
        assert test["k"] == 3
        assert test["assignments"] == 8
        assert test["exact"] is True
        assert test["p"] == pytest.approx(0.5)
        assert test["statistic"] == pytest.approx(1 / 3)

    def test_hand_computed_two_clusters(self):
        assert ss.sign_flip_test([2.0, 1.0])["p"] == pytest.approx(0.25)

    def test_ties_with_the_observed_statistic_count_toward_the_tail(self):
        # observed mean 0; both (+,+) and (-,-) reproduce it, so a strict '>' would give 0.25
        assert ss.sign_flip_test([1.0, -1.0])["p"] == pytest.approx(0.75)

    def test_a_negative_shift_can_never_be_significant(self):
        assert ss.sign_flip_test([-1.0, -2.0])["p"] == 1.0

    def test_all_positive_equal_means_give_the_smallest_exact_p(self):
        test = ss.sign_flip_test([1.0] * 4)
        assert test["p"] == pytest.approx(1 / 16)

    def test_zero_mean_clusters_inflate_k_but_not_p(self):
        assert ss.sign_flip_test([1.0])["p"] == ss.sign_flip_test([1.0, 0.0, 0.0])["p"]
        assert ss.sign_flip_test([1.0, 0.0, 0.0])["nonzero_clusters"] == 1

    def test_empty_is_not_estimable(self):
        test = ss.sign_flip_test([])
        assert test["p"] is None
        assert test["status"] == "not_estimable"

    def test_monte_carlo_branch_never_reports_p_zero(self, monkeypatch):
        monkeypatch.setattr(ss, "MONTE_CARLO_DRAWS", 2000)
        test = ss.sign_flip_test([1.0] * (ss.EXACT_SIGN_FLIP_LIMIT + 1), seed=0)
        assert test["exact"] is False
        assert test["assignments"] == 2001
        assert test["p"] == pytest.approx(1 / 2001)
        assert test["p"] > 0
        assert "Monte Carlo" in test["reason"]

    def test_monte_carlo_is_reproducible(self, monkeypatch):
        monkeypatch.setattr(ss, "MONTE_CARLO_DRAWS", 500)
        means = [float(i - 10) for i in range(25)]
        assert ss.sign_flip_test(means, seed=7) == ss.sign_flip_test(means, seed=7)

    def test_exact_limit_is_the_branch_boundary(self, monkeypatch):
        monkeypatch.setattr(ss, "EXACT_SIGN_FLIP_LIMIT", 3)
        monkeypatch.setattr(ss, "MONTE_CARLO_DRAWS", 50)
        assert ss.sign_flip_test([1.0] * 3)["exact"] is True
        assert ss.sign_flip_test([1.0] * 3)["assignments"] == 8
        assert ss.sign_flip_test([1.0] * 4)["exact"] is False
        assert ss.sign_flip_test([1.0] * 4)["assignments"] == 51


class TestHolm:
    def test_step_down_is_monotone_and_hand_computed(self):
        result = ss.holm({"a": 0.01, "b": 0.02, "c": 0.03, "d": 0.6})
        adjusted = [result["tests"][name]["p_adjusted"] for name in ("a", "b", "c", "d")]
        assert adjusted == pytest.approx([0.04, 0.06, 0.06, 0.6])
        assert adjusted == sorted(adjusted)
        assert result["rejected"] == ["a"]
        assert result["family_size"] == 4

    def test_skipped_test_does_not_shrink_the_family(self):
        result = ss.holm({"a": 0.04, "b": None})
        assert result["family_size"] == 1
        assert result["skipped"] == ["b"]
        assert result["tests"]["a"]["p_adjusted"] == pytest.approx(0.04)
        assert result["rejected"] == ["a"]
        assert "b" not in result["tests"]

    def test_counting_a_skipped_test_as_p_one_would_change_the_decision(self):
        assert ss.holm({"a": 0.04, "b": None})["rejected"] == ["a"]
        assert ss.holm({"a": 0.04, "b": 1.0})["rejected"] == []

    def test_adjusted_p_is_capped_at_one(self):
        result = ss.holm({"a": 0.9, "b": 0.95})
        assert result["tests"]["a"]["p_adjusted"] == 1.0
        assert result["tests"]["b"]["p_adjusted"] == 1.0
        assert result["rejected"] == []

    def test_empty_family(self):
        result = ss.holm({})
        assert result["family_size"] == 0
        assert result["rejected"] == []
        assert result["tests"] == {}

    def test_ties_are_broken_by_name_so_output_is_deterministic(self):
        first = ss.holm({"b": 0.01, "a": 0.01})
        second = ss.holm({"a": 0.01, "b": 0.01})
        assert first == second
        assert list(first["tests"]) == ["a", "b"]