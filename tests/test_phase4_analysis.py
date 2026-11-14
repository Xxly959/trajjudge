"""Phase 4 script tests: the failures that would make a calibration result look real.

Covers leakage between selection and evaluation, translation twins split across
folds, silently dropped undefined folds, a binary rubric given a fake AUC,
fabricated grader comments when the cache does not prove identity, false-kill
semantics inverted into agreement, and a taxonomy that leaks trace ids or loses
its ``judgment: agent`` marker.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from trajjudge import calibration as cal
from trajjudge.agreement import THRESHOLDS

from annotation_env import load_script

p4 = load_script("phase4_analysis")

ACC = "trajectory_accuracy"
COMP = "trajectory_comprehensive"
ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "reports/failure_taxonomy.md"
FROZEN_CATEGORIES = {"rubric_mismatch", "missing_evidence_check", "surface_fluency",
                     "partial_credit", "threshold_saturation", "annotation_disagreement", "other"}


def row(trace, scenario, human, acc, comp, *, official=True, task=None):
    return {"trace_id": trace, "task_id": task or scenario, "scenario_id": scenario,
            "human": human, "official": official, "scores": {ACC: acc, COMP: comp}}


def spread(*, invert=()):
    """Six scenarios, one pass and one fail each; ``invert`` flips the score order."""
    rows = []
    for k in range(6):
        flipped = k in invert
        rows.append(row(f"p{k}", f"s{k}", True, 1.0 if flipped else 3.0, 0.95))
        rows.append(row(f"f{k}", f"s{k}", False, 3.0 if flipped else 1.0, 0.55))
    return rows


def grade_row(trace, grader, score, *, prompt=100, completion=20, text=None, status="ok"):
    return {"trace_id": trace, "variant": "original", "grader": grader, "thinking": False,
            "repeat_id": 0, "judge_model": "deepseek-flash", "score": score, "status": status,
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
            "reason": "recorded reason"}


def cache_entry(trace, grader, text, *, prompt=100, completion=20, model="deepseek-flash", name="a.json"):
    tag = f"p2/{trace}/original/{grader}|think=off|direct1/0"
    return {"tag": tag, "text": text, "model": model, "prompt_tokens": prompt,
            "completion_tokens": completion, "file": name, "parts": p4.parse_tag(tag)}


def acc_text(score):
    return json.dumps({"score": score, "reason": "raw grader comment"})


def comp_text(value):
    raw = 1 + 4 * value
    return json.dumps({"step_evaluations": [
        {"step_index": 0, "step_reason": "raw step comment", "contribution_score": raw,
         "relevance_score": raw, "accuracy_score": raw, "efficiency_score": raw}]})


def blocks(rows, *, resamples=200, seed=0):
    return {"merge": p4.calibration_block(rows, resamples=resamples, seed=seed),
            "split": p4.calibration_block(rows, resamples=resamples, seed=seed)}


def joined_meta(rows):
    return {"labeled": len(rows), "selected": len(rows), "missing_scores": {ACC: 0, COMP: 0}}


def blind_key(rows):
    return {r["trace_id"]: f"B{i:06x}" for i, r in enumerate(rows)}


class TestFoldsAndVariants:
    def test_translation_twins_share_a_fold(self):
        rows = [row("a", "s0", True, 3.0, 0.95, task="T1en"),
                row("b", "s0", False, 1.0, 0.55, task="T1zh"),
                row("c", "s1", True, 3.0, 0.95, task="T2")]
        plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
        assert len(plan) == 2
        for fold in plan:
            test = {r["trace_id"] for r in fold["test"]}
            train = {r["trace_id"] for r in fold["train"]}
            assert not ({"a", "b"} & test and {"a", "b"} & train)
            assert {"a", "b"} <= test or {"a", "b"} <= train

    def test_merge_and_split_are_both_computed_and_differ(self):
        rows = [row("a", "s0", True, 3.0, 0.95, task="T1en"),
                row("b", "s0", False, 1.0, 0.55, task="T1zh")]
        merge = p4.with_scenarios(rows, {"T1en": "s0", "T1zh": "s0"})
        split = p4.with_scenarios(rows, {"T1en": "s0", "T1zh": "s0_zh"})
        assert p4.calibration_block(merge, resamples=20)["n_scenario"] == 1
        assert p4.calibration_block(split, resamples=20)["n_scenario"] == 2

    def test_with_scenarios_does_not_drop_or_reorder_rows(self):
        rows = spread()
        out = p4.with_scenarios(rows, {r["task_id"]: r["scenario_id"] for r in rows})
        assert [r["trace_id"] for r in out] == [r["trace_id"] for r in rows]


class TestNoLeakage:
    def test_held_out_labels_cannot_change_their_own_threshold(self):
        # s0 is separable only at 2.5; every other scenario is separable at 2.0.
        # Selecting on all rows would pick 2.5 and score s0 perfectly. LOSO must
        # pick 2.0 for the s0 fold and therefore mispredict s0's failure.
        rows = [row("p0", "s0", True, 3.0, 0.95), row("f0", "s0", False, 2.0, 0.55)]
        for k in range(1, 6):
            rows += [row(f"p{k}", f"s{k}", True, 3.0, 0.95), row(f"f{k}", f"s{k}", False, 1.0, 0.55)]
        plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
        result = cal.out_of_fold(plan, ACC)
        fold0 = next(f for f in result["folds"] if f["scenario_id"] == "s0")
        assert fold0["threshold"] == "threshold:2.0"
        preds = {r["trace_id"]: r["pred"] for r in result["oof"] if r["scenario_id"] == "s0"}
        assert preds == {"p0": True, "f0": True}
        assert cal.select(rows, ACC)["threshold"] == "threshold:2.5"

    def test_every_oof_prediction_comes_from_a_fold_that_excluded_its_scenario(self):
        rows = spread(invert=(2,))
        plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
        result = cal.out_of_fold(plan, ACC)
        assert len(result["oof"]) == len(rows)
        for fold in plan:
            assert {r["trace_id"] for r in fold["train"]}.isdisjoint({r["trace_id"] for r in fold["test"]})


class TestDefaultThreshold:
    def test_missing_scores_are_skipped_not_imputed(self):
        rows = spread()
        rows[0]["scores"][ACC] = None
        out = p4.at_default(rows, ACC)
        assert len(out) == len(rows) - 1
        assert all(r["score"] is not None for r in out)

    def test_default_predictions_use_the_frozen_upstream_thresholds(self):
        rows = [row("a", "s0", True, 2.0, 0.6), row("b", "s0", False, 1.99, 0.599)]
        out = {r["trace_id"]: r for r in p4.at_default(rows, ACC)}
        assert out["a"]["pred"] is True and out["b"]["pred"] is False
        comp = {r["trace_id"]: r for r in p4.at_default(rows, COMP)}
        assert comp["a"]["pred"] is True and comp["b"]["pred"] is False
        assert all(r["fallback"] is False for r in out.values())


class TestFrameworkIsBinary:
    def test_auc_and_pr_auc_are_refused_not_filled_with_half(self):
        out = p4.framework_summary(spread(), resamples=50)
        assert out["auc_pass"] is None and out["auc_fail"] is None and out["pr_auc_fail"] is None
        assert out["auc_reason"] == p4.BINARY_ONLY == out["pr_auc_reason"]

    def test_markdown_never_prints_a_numeric_framework_auc(self):
        rows = spread(invert=(0, 1, 2))
        block = blocks(rows)
        framework = p4.framework_summary(rows, resamples=50)
        text = p4.markdown(block, framework, {"definition": "d", "n_traj": 0, "n_scenario": 0,
                                             "scenarios": [], "case_study": True},
                           p4.hybrid_block(rows, blind_key(rows)), joined_meta(rows))
        assert p4.BINARY_ONLY in text
        for line in text.splitlines():
            if line.startswith("| framework"):
                cells = [c.strip() for c in line.split("|")]
                assert "0.5000" not in cells[-3:-1]


class TestUndefinedFolds:
    def test_single_class_training_fold_is_counted_and_falls_back_loudly(self):
        rows = [row(f"t{k}", f"s{k}", True, 3.0, 0.95) for k in range(6)]
        plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
        arms = p4._arms(cal.out_of_fold(plan, ACC), resamples=20, seed=0)
        assert arms["undefined_folds"] == 6
        assert arms["undefined_share"] == 1.0
        assert arms["fallback_folds"] == [f"s{k}" for k in range(6)]
        assert arms["calibrated_only"]["n_oof"] == 0
        assert arms["with_fallback"]["n_oof"] == 6
        assert arms["with_fallback"]["fallback_rows"] == 6

    def test_undefined_folds_are_not_silently_dropped_from_the_primary_arm(self):
        rows = spread()
        rows += [row(f"x{k}", f"s{k}", True, 3.0, 0.95) for k in range(6, 9)]
        plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
        arms = p4._arms(cal.out_of_fold(plan, ACC), resamples=20, seed=0)
        assert arms["with_fallback"]["n_oof"] == len(rows)
        assert arms["calibrated_only"]["n_oof"] <= arms["with_fallback"]["n_oof"]

    def test_when_no_fold_is_undefined_the_two_arms_coincide(self):
        rows = spread()
        plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
        arms = p4._arms(cal.out_of_fold(plan, ACC), resamples=20, seed=0)
        assert arms["undefined_folds"] == 0
        assert arms["calibrated_only"]["n_oof"] == arms["with_fallback"]["n_oof"] == len(rows)


class TestRecoverRaw:
    def test_valid_entry_is_accepted_and_parsed(self):
        rows = [grade_row("t1", ACC, 3.0)]
        out = p4.recover_raw(rows, [cache_entry("t1", ACC, acc_text(3.0))])
        rec = out["t1|" + ACC]
        assert rec["recovered"] is True and rec["verified"] == 1
        assert rec["raw"]["reason"] == "raw grader comment"

    def test_comprehensive_score_is_recomputed_not_trusted(self):
        rows = [grade_row("t1", COMP, 0.75)]
        out = p4.recover_raw(rows, [cache_entry("t1", COMP, comp_text(0.75))])
        assert out["t1|" + COMP]["recovered"] is True

    def test_absent_cache_is_reported_as_unrecoverable(self):
        out = p4.recover_raw([grade_row("t1", ACC, 3.0)], [])
        rec = out["t1|" + ACC]
        assert rec["recovered"] is False and rec["reason"] == "原始输出不可得"
        assert "raw" not in rec

    def test_matching_tag_with_wrong_tokens_is_rejected(self):
        rows = [grade_row("t1", ACC, 3.0, prompt=100)]
        out = p4.recover_raw(rows, [cache_entry("t1", ACC, acc_text(3.0), prompt=999)])
        assert out["t1|" + ACC]["recovered"] is False
        assert out["t1|" + ACC]["candidates"] == 1 and out["t1|" + ACC]["verified"] == 0

    def test_matching_tokens_with_wrong_score_is_rejected(self):
        rows = [grade_row("t1", ACC, 3.0)]
        out = p4.recover_raw(rows, [cache_entry("t1", ACC, acc_text(1.0))])
        assert out["t1|" + ACC]["recovered"] is False

    def test_two_verified_but_different_texts_are_not_guessed_between(self):
        rows = [grade_row("t1", ACC, 3.0)]
        entries = [cache_entry("t1", ACC, acc_text(3.0), name="a.json"),
                   cache_entry("t1", ACC, json.dumps({"score": 3.0, "reason": "different"}), name="b.json")]
        rec = p4.recover_raw(rows, entries)["t1|" + ACC]
        assert rec["verified"] == 2 and rec["recovered"] is False
        assert "内容不同" in rec["reason"]

    def test_unparseable_text_does_not_crash_or_get_imputed(self):
        rows = [grade_row("t1", ACC, 3.0)]
        out = p4.recover_raw(rows, [cache_entry("t1", ACC, "not json")])
        assert out["t1|" + ACC]["recovered"] is False

    def test_other_phases_and_graders_are_not_pooled_in(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps(
            {"tag": "p4/t1/original/trajectory_accuracy|think=off|direct1/0", "text": acc_text(3.0)}), encoding="utf-8")
        (tmp_path / "b.json").write_text(json.dumps(
            {"tag": "p2/t1/original/trajectory_vibes|think=off|direct1/0", "text": acc_text(3.0)}), encoding="utf-8")
        (tmp_path / "c.json").write_text(json.dumps(
            {"tag": "p2/t1/original/trajectory_accuracy|think=off|direct1/0", "text": acc_text(3.0)}), encoding="utf-8")
        assert [e["file"] for e in p4.load_cache(tmp_path)] == ["c.json"]


class TestHybridVerdict:
    def test_framework_passing_every_human_pass_is_agreement_not_false_kills(self):
        rows = spread()
        out = p4.hybrid_block(rows, blind_key(rows))
        assert out["framework_false_fail_on_human_pass"] == 0
        assert out["n_human_pass"] == 6

    def test_disjoint_misses_with_a_better_union_support_hybrid_scoring(self):
        rows = []
        for k in range(6):
            rows.append(row(f"p{k}", f"s{k}", True, 3.0, 0.95, official=True))
            # A catch means the grader scored the failure BELOW its threshold.
            # framework catches the even failures; accuracy catches only s5.
            caught_by_framework = k % 2 == 0
            rows.append(row(f"f{k}", f"s{k}", False, 1.0 if k == 5 else 3.0, 0.95,
                            official=not caught_by_framework))
        out = p4.hybrid_block(rows, blind_key(rows))
        assert out["caught_by"]["framework"] == 3
        assert out["caught_by"][ACC] == 1
        assert out["both"] == [] and out["caught_union"] == 4
        assert out["support"] is True and out["against"] is False
        assert out["verdict"] == "有支持证据"

    def test_fewer_than_five_failure_scenarios_is_a_case_study(self):
        rows = [row(f"t{k}", f"s{k % 2}", False, 3.0, 0.95, official=False) for k in range(6)]
        out = p4.hybrid_block(rows, blind_key(rows))
        assert out["n_scenario_fail"] == 2
        assert out["verdict"] == "证据不足，不下结论"

    def test_support_and_against_together_do_not_produce_a_verdict(self):
        rows = []
        for k in range(6):
            rows.append(row(f"p{k}", f"s{k}", True, 3.0, 0.95, official=False))
            rows.append(row(f"f{k}", f"s{k}", False, 3.0 if k == 5 else 1.0, 0.95,
                            official=k % 2 == 0))
        out = p4.hybrid_block(rows, blind_key(rows))
        assert out["support"] is True and out["against"] is True
        assert out["verdict"] == "支持与反对证据并存，不下结论"

    def test_no_human_failures_does_not_crash_on_an_empty_rate_list(self):
        rows = [row(f"p{k}", f"s{k}", True, 3.0, 0.95) for k in range(6)]
        out = p4.hybrid_block(rows, blind_key(rows))
        assert out["n_human_fail"] == 0
        assert out["verdict"] == "证据不足，不下结论"

    def test_a_missing_grade_is_neither_a_catch_nor_a_kill(self):
        rows = spread()
        rows[1]["scores"][ACC] = None
        out = p4.hybrid_block(rows, blind_key(rows))
        assert out["n_human_fail"] == 6
        assert out["grader_false_fail_on_human_pass"][ACC] == 0

    def test_membership_lists_carry_blind_ids_not_trace_ids(self):
        rows = spread(invert=(0,))
        out = p4.hybrid_block(rows, blind_key(rows))
        listed = out["framework_only"] + out["graders_only"] + out["neither"] + out["both"]
        assert listed
        assert all(re.fullmatch(r"B[0-9a-f]{6}", b) for b in listed)
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                             json.dumps(out, ensure_ascii=False))

    def test_an_unmapped_trace_raises_instead_of_leaking_its_id(self):
        rows = spread(invert=(0,))
        with pytest.raises(KeyError):
            p4.hybrid_block(rows, {})


class TestHardSampleBlock:
    def test_missing_trace_item_yields_no_fabricated_evidence(self):
        rows = [row("f0", "s0", False, 3.0, 0.95, official=True)]
        out = p4.hard_sample_block(rows, {}, {}, [], {"f0": "Baaaaaa"}, {"s0": "s0"})
        rec = out["records"][0]
        assert rec["evidence"] == [] and rec["evidence_available"] is False
        assert rec["graders"][ACC]["reason"] == "原始输出不可得（无缓存记录）"

    def test_human_reason_text_is_never_emitted_only_its_availability(self):
        rows = [row("f0", "s0", False, 3.0, 0.95, official=True)]
        labels = [{"blind_id": "Baaaaaa", "round": "1", "reason": "秘密理由原文"}]
        out = p4.hard_sample_block(rows, {}, {}, labels, {"f0": "Baaaaaa"}, {"s0": "s0"})
        assert out["records"][0]["human_reason_available"] is True
        assert "秘密理由原文" not in json.dumps(out, ensure_ascii=False)

    def test_round2_reasons_do_not_count_as_round1_availability(self):
        rows = [row("f0", "s0", False, 3.0, 0.95, official=True)]
        labels = [{"blind_id": "Baaaaaa", "round": "2", "reason": "second round"}]
        out = p4.hard_sample_block(rows, {}, {}, labels, {"f0": "Baaaaaa"}, {"s0": "s0"})
        assert out["records"][0]["human_reason_available"] is False

    def test_case_study_flag_follows_the_scenario_count(self):
        rows = [row(f"f{k}", f"s{k % 3}", False, 3.0, 0.95, official=True) for k in range(6)]
        out = p4.hard_sample_block(rows, {}, {}, [], {}, {f"s{k}": f"s{k}" for k in range(3)})
        assert out["n_traj"] == 6 and out["n_scenario"] == 3 and out["case_study"] is True


class TestAucVerdict:
    def test_covering_half_means_no_usable_discrimination(self):
        assert p4._auc_verdict({"auc_covers_half": True}) == "是 → 无证据支持可用区分度"

    def test_excluding_half_is_reported_as_no(self):
        assert p4._auc_verdict({"auc_covers_half": False}) == "否"

    def test_unestimable_is_not_rendered_as_evidence_of_discrimination(self):
        verdict = p4._auc_verdict({"auc_covers_half": None})
        assert verdict.startswith("不可估")
        assert verdict != "否"

    def test_missing_key_is_treated_as_unestimable(self):
        assert p4._auc_verdict({}).startswith("不可估")


class TestMarkdown:
    @pytest.fixture()
    def text(self):
        rows = spread(invert=(0, 1, 2))
        block = blocks(rows)
        framework = p4.framework_summary(rows, resamples=50)
        hard = {"definition": "human fail ∧ framework passed", "n_traj": 2, "n_scenario": 2,
                "scenarios": ["s0", "s1"], "case_study": True}
        return p4.markdown(block, framework, hard, p4.hybrid_block(rows, blind_key(rows)), joined_meta(rows))

    def test_provisional_banner_and_gate_a_are_stated(self, text):
        assert "PROVISIONAL" in text and "闸门 A 未通过" in text and "exploratory" in text

    def test_every_table_row_has_the_same_column_count_as_its_header(self, text):
        header = None
        for line in text.splitlines():
            if not line.startswith("|"):
                header = None
                continue
            columns = len(re.split(r"(?<!\\)\|", line)) - 2
            if header is None:
                header = columns
            else:
                assert columns == header, f"torn table row: {line}"

    def test_degenerate_sentinel_units_are_warned_about_by_name(self, text):
        assert "退化警告" in text
        assert f"merge/{ACC}/miss_0.10" in text
        assert "sensitivity = 0" in text

    def test_non_degenerate_grader_is_not_listed_in_the_warning(self, text):
        warning = text.split("退化警告")[1].split("\n\n")[0]
        assert COMP not in warning

    def test_effect_size_is_stated_in_counts_not_percentage_points(self, text):
        assert "效应量" in text
        assert re.search(r"多抓 \d+ 条 human fail", text)

    def test_both_scenario_variants_are_rendered(self, text):
        assert "`merge`（主口径）" in text and "`split`（敏感性口径）" in text

    def test_both_arms_are_rendered_for_every_objective(self, text):
        for variant in ("merge", "split"):
            for grader in THRESHOLDS:
                for name, _ in p4.OBJECTIVES:
                    for arm in ("calibrated_only", "with_fallback"):
                        assert f"| {variant} | {grader} | {name} | {arm} |" in text

    def test_primary_miss_rate_is_marked(self, text):
        assert f"{cal.PRIMARY_MISS_RATE:.2f}（主值）" in text

    def test_negative_zero_is_not_printed(self):
        assert p4._fmt(-0.0) == "0.0000"
        assert p4._fmt(None) == "—"

    def test_unestimable_interval_is_labelled_not_rendered_as_a_number(self):
        assert "not_estimable" in p4._ci({"ci": None, "status": "not_estimable", "reason": "不可估（簇数不足）"})
        assert p4._ci(None) == "—"

    def test_pipe_in_a_cell_is_escaped(self):
        assert p4._escape("a|b") == "a\\|b"


@pytest.mark.skipif(not TAXONOMY.exists(), reason="taxonomy artefact not generated")
class TestTaxonomyArtefact:
    @pytest.fixture()
    def text(self):
        return TAXONOMY.read_text(encoding="utf-8")

    def test_every_entry_carries_a_frozen_category_and_the_agent_marker(self, text):
        entries = re.split(r"\n### ", text)[1:]
        assert entries
        for entry in entries:
            category = re.search(r"^- 类别：`(\w+)`", entry, re.M)
            assert category, entry.splitlines()[0]
            assert category.group(1) in FROZEN_CATEGORIES
            assert "`judgment: agent`" in entry

    def test_declared_counts_match_the_entries(self, text):
        entries = re.split(r"\n### ", text)[1:]
        declared = int(re.search(r"\*\*n_traj = (\d+)", text).group(1))
        assert declared == len(entries)
        scenarios = {re.match(r"B[0-9a-f]{6} — (\S+)", e).group(1) for e in entries}
        assert int(re.search(r"n_scenario = (\d+)\*\*", text).group(1)) == len(scenarios)

    def test_category_table_matches_the_per_entry_categories(self, text):
        entries = re.split(r"\n### ", text)[1:]
        actual = {}
        for entry in entries:
            name = re.search(r"^- 类别：`(\w+)`", entry, re.M).group(1)
            actual[name] = actual.get(name, 0) + 1
        for name, count in actual.items():
            line = next(l for l in text.splitlines() if l.startswith(f"| `{name}`"))
            assert int(line.split("|")[2].strip()) == count

    def test_no_trace_id_value_or_trace_path_leaks_into_the_tracked_file(self, text):
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)
        assert "outputs/claw_eval" not in text
        assert '"trace_id"' not in text

    def test_entries_are_addressed_by_blind_id_only(self, text):
        for heading in re.findall(r"\n### (\S+) —", text):
            assert re.fullmatch(r"B[0-9a-f]{6}", heading), heading

    def test_every_entry_cites_message_numbered_evidence_and_a_grader_quote(self, text):
        for entry in re.split(r"\n### ", text)[1:]:
            assert re.search(r"`\[\d+\]`", entry), entry.splitlines()[0]
            assert "评分器原话摘录" in entry

    def test_propagation_boundary_is_declared(self, text):
        assert "round2 完成前不得进入" in text
        assert "exploratory" in text and "PROVISIONAL" in text


@pytest.mark.skipif(not (ROOT / "reports/phase4_calibration.json").exists(),
                    reason="calibration artefact not generated")
class TestTrackedCalibrationArtefact:
    def test_no_trace_id_leaks_into_the_tracked_aggregate(self):
        text = (ROOT / "reports/phase4_calibration.json").read_text(encoding="utf-8")
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)

    def test_membership_lists_are_blind_ids(self):
        payload = json.loads((ROOT / "reports/phase4_calibration.json").read_text(encoding="utf-8"))
        hybrid = payload["hybrid_scoring"]
        listed = hybrid["framework_only"] + hybrid["graders_only"] + hybrid["neither"] + hybrid["both"]
        assert all(re.fullmatch(r"B[0-9a-f]{6}", b) for b in listed)
        assert len(listed) == hybrid["n_human_fail"]

    def test_status_is_provisional_and_exploratory(self):
        payload = json.loads((ROOT / "reports/phase4_calibration.json").read_text(encoding="utf-8"))
        assert payload["status"] == "provisional"
        assert "exploratory" in payload["status_note"]
        assert payload["raw_recovery"]["api_calls"] == 0
        assert payload["raw_recovery"]["new_cost_usd"] == 0.0


class TestNoLeakIntoAnnotationPaths:
    def test_guide_and_kit_contain_no_taxonomy_content(self):
        guide = ROOT / "annotation/GUIDE.md"
        if not guide.exists():
            pytest.skip("round2 kit not built yet")
        text = guide.read_text(encoding="utf-8")
        assert "failure_taxonomy" not in text
        for category in FROZEN_CATEGORIES:
            assert category not in text
        if TAXONOMY.exists():
            for blind in re.findall(r"\n### (B[0-9a-f]{6}) —", TAXONOMY.read_text(encoding="utf-8")):
                assert blind not in text