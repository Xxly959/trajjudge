"""Phase 3 script: scenario variants, pool census, gate B, dry-run evidence, report text.

The traps covered here are the ones that would silently inflate a result: counting
translation twins as independent scenarios for gate B, letting framework `passed`
stand in for a human label, overwriting an owner's blind batch, reporting a cache
miss as a clean replay, or a report whose prose contradicts its own tables.
"""
from __future__ import annotations

import csv
import json
import re

import pytest

from annotation_env import load_script

BASE = {"trajectory_accuracy": 1.5, "trajectory_comprehensive": 0.7}
SHIFT = {"trajectory_accuracy": 1.0, "trajectory_comprehensive": 0.2}
VARIANTS = ("L1_note/tool_result", "L2_request/tool_result")
GRADERS = ("trajectory_accuracy", "trajectory_comprehensive")


def make_row(trace, variant, score, *, grader, repeat=0, defended=False, task_id, status="ok", reason=None):
    return {"trace_id": trace, "variant": variant, "score": score, "grader": grader, "repeat_id": repeat,
            "defended": defended, "status": status, "reason": reason, "task_id": task_id,
            "config": "cfg|def" if defended else "cfg", "judge_model": "m", "max_tokens": 1000,
            "openjudge_commit": "c", "job_id": f"{trace}|{variant}|{grader}|{repeat}|{int(defended)}"}


def synth(*, scenarios=5, twins=2, variants=VARIANTS, graders=GRADERS, arms=(False,), repeats=1,
          positive_only=False):
    rows, mapping = [], {}
    for index in range(scenarios):
        for twin in range(twins):
            task = f"T{index:03d}{'zh' if twin else 'en'}_demo"
            trace = f"trace-{index}-{twin}"
            mapping[task] = f"scenario{index}"
            for grader in graders:
                for arm in arms:
                    for variant in ("original", *variants):
                        for repeat in range(repeats):
                            delta = 0.0 if variant == "original" else (
                                SHIFT[grader] if positive_only or index % 2 == 0 else -SHIFT[grader])
                            rows.append(make_row(trace, variant, BASE[grader] + delta, grader=grader,
                                                 repeat=repeat, defended=arm, task_id=task))
    return rows, mapping


def census(entries, *, never=()):
    """entries: (trace_id, task_id, scenario_id, human label); framework fields are always 'passed'."""
    candidates = [{"trace_id": t, "task_id": k, "passed": True, "task_score": 1.0} for t, k, _s, _l in entries]
    chosen = [c for c in candidates if c["trace_id"] not in never]
    key = {t: f"B{i:06x}" for i, (t, _k, _s, _l) in enumerate(entries)}
    labels = [{"blind_id": key[t], "label": label, "reason": "fixture reason", "annotated_at": "now", "round": "1"}
              for t, _k, _s, label in entries if t not in never]
    return candidates, chosen, labels, key, {k: s for _t, k, s, _l in entries}


def items_of(rows, mapping):
    seen = {}
    for row in rows:
        seen[row["trace_id"]] = (row["trace_id"], row["task_id"], mapping[row["task_id"]], "fail")
    return list(seen.values())


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def report_parts(tmp_path, *, scenarios=5, estimate=10.9, error_rows=0, replay=True, positive_only=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    cli = load_script("phase3_analysis")
    rows, mapping = synth(scenarios=scenarios, arms=(False, True), positive_only=positive_only)
    entries = items_of(rows, mapping)
    candidates, chosen, labels, key, _cmap = census(entries)
    pool = {name: cli.pool_stats(candidates, chosen, labels, key, mapping) for name in ("merge", "split")}
    pool["primary_variant"] = "merge"
    analyses = {name: cli.injection_analysis(rows, mapping, resamples=100, seed=0) for name in ("merge", "split")}
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"jobs": len(rows), "completions": len(rows),
                                "peak_cap_based_estimate_usd": estimate}), encoding="utf-8")
    published = tmp_path / "published.jsonl"
    write_jsonl(published, rows)
    replay_path = tmp_path / "replay.jsonl"
    if replay:
        replay_rows = [dict(r) for r in rows]
        marked = 0
        for row in replay_rows:
            if marked >= error_rows:
                break
            if row["grader"] == "trajectory_comprehensive" and row["variant"] != "original" and row["defended"]:
                row.update(status="error", score=None,
                           reason="raw verdict invalid (upstream may have clamped it): step_evaluations missing")
                marked += 1
        write_jsonl(replay_path, replay_rows)
    dry = cli.dry_run_section(plan, published, replay_path if replay else None)
    return {"cli": cli, "pool": pool, "analyses": analyses, "dry": dry, "rows": rows, "mapping": mapping,
            "plan": plan, "published": published, "replay": replay_path}


class TestScenarioVariants:
    def files(self, tmp_path, uncertain):
        csv_path = tmp_path / "scenario_map.csv"
        csv_path.write_text("task_id,scenario_id\nT159zh_vip,vip\nT160_vip,vip\nT001en_other,other\n",
                            encoding="utf-8")
        json_path = tmp_path / "uncertain.json"
        json_path.write_text(json.dumps(uncertain), encoding="utf-8")
        return csv_path, json_path

    def test_split_only_separates_pairs_awaiting_owner_confirmation(self, tmp_path):
        cli = load_script("phase3_analysis")
        csv_path, json_path = self.files(tmp_path, [
            {"task_ids": ["T159zh_vip", "T160_vip"], "recommendation": "owner confirmation required: same structure"},
            {"task_ids": ["T001en_other"], "recommendation": "resolved: genuinely distinct"}])
        variants = cli.scenario_variants(csv_path, json_path)
        assert variants["merge"]["T159zh_vip"] == variants["merge"]["T160_vip"] == "vip"
        assert variants["split"]["T159zh_vip"] == "vip__T159zh_vip"
        assert variants["split"]["T160_vip"] == "vip__T160_vip"
        assert variants["split"]["T001en_other"] == "other"
        assert variants["flagged"] == [["T159zh_vip", "T160_vip"]]

    def test_no_flagged_pairs_means_both_variants_are_identical(self, tmp_path):
        cli = load_script("phase3_analysis")
        csv_path, json_path = self.files(tmp_path, [])
        variants = cli.scenario_variants(csv_path, json_path)
        assert variants["merge"] == variants["split"]
        assert variants["flagged"] == []


class TestPoolCensus:
    def test_gate_b_counts_scenarios_not_trajectories(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=4, twins=3, variants=(), graders=("trajectory_accuracy",))
        entries = [(t, k, s, "fail") for t, k, s, _l in items_of(rows, mapping)]
        pool = cli.pool_stats(*census(entries)[:4], mapping)
        assert pool["human_fail"]["n_traj"] == 12
        assert pool["human_fail"]["n_scenario"] == 4
        assert pool["gate_b"]["triggered"] is True

    def test_gate_b_not_triggered_at_ten_independent_scenarios(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=10, twins=2, variants=(), graders=("trajectory_accuracy",))
        pool = cli.pool_stats(*census(items_of(rows, mapping))[:4], mapping)
        assert pool["human_fail"]["n_traj"] == 20
        assert pool["human_fail"]["n_scenario"] == 10
        assert pool["gate_b"]["triggered"] is False

    def test_blank_and_never_selected_rows_are_unlabeled_not_fail(self, tmp_path):
        cli = load_script("phase3_analysis")
        entries = [(f"t{i}", f"T{i:03d}_demo", f"scenario{i}", label)
                   for i, label in enumerate(("fail", "fail", "", "pass"))]
        entries.append(("t4", "T004_demo", "scenario4", "fail"))
        candidates, chosen, labels, key, mapping = census(entries, never=("t4",))
        pool = cli.pool_stats(candidates, chosen, labels, key, mapping)
        assert pool["human_fail"]["n_traj"] == 2
        assert pool["blank_in_selected"] == [key["t2"]]
        assert pool["never_selected"] == 1
        assert pool["unlabeled_total"] == 2
        assert pool["labeled"] == 3
        assert pool["unlabeled_pool"]["n_scenario"] == 2

    def test_framework_passed_is_never_a_substitute_for_a_human_label(self, tmp_path):
        cli = load_script("phase3_analysis")
        entries = [("t0", "T000_demo", "scenario0", "fail"), ("t1", "T001_demo", "scenario1", "pass")]
        candidates, chosen, labels, key, mapping = census(entries)
        assert all(c["passed"] is True and c["task_score"] == 1.0 for c in candidates)
        pool = cli.pool_stats(candidates, chosen, labels, key, mapping)
        assert pool["human_fail"]["trace_ids"] == ["t0"]

    def test_status_is_provisional(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=2, variants=(), graders=("trajectory_accuracy",))
        pool = cli.pool_stats(*census(items_of(rows, mapping))[:4], mapping)
        assert pool["status"] == "provisional"

    def test_merge_split_disagreement_outside_the_fail_pool_does_not_move_gate_b(self, tmp_path):
        cli = load_script("phase3_analysis")
        entries = [(f"t{i}", f"T{i:03d}_demo", f"scenario{i}", "fail") for i in range(10)]
        entries += [("vip_zh", "T159zh_vip", "vip", "pass"), ("vip_en", "T160_vip", "vip", "pass")]
        candidates, chosen, labels, key, merge = census(entries)
        split = dict(merge, **{"T159zh_vip": "vip__T159zh_vip", "T160_vip": "vip__T160_vip"})
        merged = cli.pool_stats(candidates, chosen, labels, key, merge)
        splitted = cli.pool_stats(candidates, chosen, labels, key, split)
        assert merged["candidate_scenarios"] == 11
        assert splitted["candidate_scenarios"] == 12
        assert merged["human_fail"] == splitted["human_fail"]
        assert merged["gate_b"] == splitted["gate_b"]


class TestBlindBatch:
    def test_batch_is_blank_and_key_is_separate(self, tmp_path):
        cli = load_script("phase3_analysis")
        csv_path = tmp_path / "annotation" / "batch_extra.csv"
        key_path = tmp_path / "outputs" / "batch_extra_key.json"
        result = cli.write_blind_batch([f"t{i}" for i in range(5)], csv_path, key_path)
        with csv_path.open(newline="", encoding="utf-8") as handle:
            written = list(csv.DictReader(handle))
        assert len(written) == 5
        assert all(r["label"] == "" and r["reason"] == "" and r["annotated_at"] == "" for r in written)
        key = json.loads(key_path.read_text(encoding="utf-8"))
        assert len(set(key.values())) == 5
        assert all(v.startswith("B") and len(v) == 7 for v in key.values())
        assert set(key.values()) == {r["blind_id"] for r in written}
        assert result["rows"] == 5
        assert result["views_rendered"] is False
        assert "5" in result["note"]
        assert key_path.parent != csv_path.parent

    def test_refuses_to_overwrite_an_existing_csv(self, tmp_path):
        cli = load_script("phase3_analysis")
        csv_path = tmp_path / "batch_extra.csv"
        key_path = tmp_path / "key.json"
        cli.write_blind_batch(["t0"], csv_path, key_path)
        before = csv_path.read_text(encoding="utf-8")
        with pytest.raises(SystemExit):
            cli.write_blind_batch(["t0", "t1"], csv_path, key_path)
        assert csv_path.read_text(encoding="utf-8") == before

    def test_refuses_to_overwrite_when_only_the_key_exists(self, tmp_path):
        cli = load_script("phase3_analysis")
        key_path = tmp_path / "key.json"
        key_path.write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit):
            cli.write_blind_batch(["t0"], tmp_path / "batch_extra.csv", key_path)
        assert not (tmp_path / "batch_extra.csv").exists()


class TestDryRun:
    def test_identical_replay_is_cache_coverage_evidence(self, tmp_path):
        parts = report_parts(tmp_path)
        replay = parts["dry"]["replay"]
        assert replay["identical"] is True
        assert replay["same_job_set"] is True
        assert replay["score_status_reason_differences"] == 0
        assert replay["cache_misses"] == 0
        assert parts["dry"]["new_api_calls"] == 0
        assert parts["dry"]["new_cost_usd"] == 0.0

    def test_a_changed_score_breaks_identity(self, tmp_path):
        parts = report_parts(tmp_path)
        rows = [dict(r) for r in parts["rows"]]
        rows[0]["score"] = rows[0]["score"] + 1.0
        write_jsonl(parts["replay"], rows)
        replay = parts["cli"].dry_run_section(parts["plan"], parts["published"], parts["replay"])["replay"]
        assert replay["identical"] is False
        assert replay["score_status_reason_differences"] == 1

    def test_a_missing_job_breaks_the_job_set(self, tmp_path):
        parts = report_parts(tmp_path)
        write_jsonl(parts["replay"], parts["rows"][:-1])
        replay = parts["cli"].dry_run_section(parts["plan"], parts["published"], parts["replay"])["replay"]
        assert replay["same_job_set"] is False
        assert replay["identical"] is False
        assert replay["replay_rows"] == len(parts["rows"]) - 1

    def test_cache_miss_reason_is_counted(self, tmp_path):
        parts = report_parts(tmp_path)
        rows = [dict(r) for r in parts["rows"]]
        rows[0].update(status="error", score=None, reason="offline mode: completion cache miss")
        write_jsonl(parts["replay"], rows)
        replay = parts["cli"].dry_run_section(parts["plan"], parts["published"], parts["replay"])["replay"]
        assert replay["cache_misses"] == 1
        assert replay["identical"] is False
        assert replay["error_rows_by_arm"]["undefended"] == 1
        assert replay["error_rows_by_arm"]["defended"] == 0

    def test_error_rows_are_reported_by_arm_and_reason(self, tmp_path):
        parts = report_parts(tmp_path, error_rows=3)
        replay = parts["dry"]["replay"]
        assert replay["error_rows_replay"] == 3
        assert replay["error_rows_by_arm"]["defended"] == 3
        assert replay["error_rows_by_arm"]["undefended"] == 0
        assert sum(replay["error_reasons_replay"].values()) == 3
        assert replay["rows_by_arm"]["defended"] == replay["rows_by_arm"]["undefended"]

    def test_latest_retry_supersedes_an_earlier_error_row(self, tmp_path):
        parts = report_parts(tmp_path)
        rows = [dict(r) for r in parts["rows"]]
        failed = dict(rows[0], status="error", score=None, reason="raw verdict invalid")
        write_jsonl(parts["replay"], [failed] + rows)
        replay = parts["cli"].dry_run_section(parts["plan"], parts["published"], parts["replay"])["replay"]
        assert replay["replay_rows"] == len(rows)
        assert replay["identical"] is True

    def test_absent_replay_is_reported_as_unverified(self, tmp_path):
        parts = report_parts(tmp_path, replay=False)
        assert parts["dry"]["replay"] is None
        assert parts["dry"]["new_cost_usd"] == 0.0


class TestInjectionAnalysis:
    def test_confirmatory_family_is_the_undefended_arm_only(self, tmp_path):
        parts = report_parts(tmp_path)
        analysis = parts["analyses"]["merge"]
        family = analysis["confirmatory_family"]
        assert family["family_size"] == len(GRADERS) * len(VARIANTS)
        assert len(analysis["defended_arm_descriptive"]) == len(GRADERS) * len(VARIANTS)
        assert len(analysis["units"]) == 2 * len(GRADERS) * len(VARIANTS)
        assert family["skipped"] == []
        assert analysis["status"] == "provisional"

    def test_a_cell_with_too_few_scenarios_is_skipped_not_tested(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=5, arms=(False,))
        keep = [r for r in rows if not (r["variant"] == "L2_request/tool_result"
                                        and mapping[r["task_id"]] in ("scenario3", "scenario4"))]
        analysis = cli.injection_analysis(keep, mapping, resamples=100, seed=0)
        family = analysis["confirmatory_family"]
        assert "trajectory_accuracy|L2_request/tool_result" in family["skipped"]
        assert family["family_size"] == 2 * len(VARIANTS) - 2
        small = next(u for u in analysis["units"] if u["variant"] == "L2_request/tool_result"
                     and u["grader"] == "trajectory_accuracy")
        assert small["rates"]["n_scenario"] == 3
        assert small["rates"]["case_study"] is True
        assert small["rates"]["rates"]["asr_flip"] is None

    def test_rows_without_task_id_cannot_be_clustered(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=5)
        for row in rows:
            del row["task_id"]
        with pytest.raises(ValueError, match="task_id"):
            cli.injection_analysis(rows, mapping, resamples=50, seed=0)

    def test_unpaired_observations_are_kept_visible(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=5)
        rows = [r for r in rows if not (r["variant"] == "original" and r["trace_id"] == "trace-0-0")]
        analysis = cli.injection_analysis(rows, mapping, resamples=50, seed=0)
        assert analysis["unpaired_observations"] == 2 * len(VARIANTS)

    def test_baseline_fail_summary_uses_trajectory_and_scenario_counts(self, tmp_path):
        parts = report_parts(tmp_path)
        entry = parts["analyses"]["merge"]["baseline_fail"]["trajectory_accuracy|raw"]
        assert entry["n_traj"] == 10
        assert entry["n_scenario"] == 5
        assert entry["fail_to_pass_traj"] == 6
        assert entry["case_study"] is False
        saturated = parts["analyses"]["merge"]["baseline_fail"]["trajectory_comprehensive|def"]
        assert saturated["n_traj"] == 0


class TestMarkdown:
    def test_provisional_banner_and_forbidden_deliverables(self, tmp_path):
        parts = report_parts(tmp_path)
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert "PROVISIONAL" in text
        assert "不得写入 FINAL_REPORT_v2 / RESUME_CLAIMS" in text

    def test_test_names_are_escaped_so_tables_do_not_split(self, tmp_path):
        parts = report_parts(tmp_path, scenarios=10, positive_only=True)
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert parts["analyses"]["merge"]["confirmatory_family"]["rejected"]
        assert "trajectory_comprehensive\\|L1_note/tool_result" in text
        block: list[int] = []
        for line in text.splitlines() + [""]:
            if line.startswith("|"):
                block.append(len(re.split(r"(?<!\\)\|", line)) - 2)
            elif block:
                assert len(set(block)) == 1, f"ragged markdown table: {block}"
                block = []

    def test_gate_b_sentence_follows_the_data(self, tmp_path):
        parts = report_parts(tmp_path, scenarios=3)
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert "闸门 B 触发" in text
        assert "都不触发" not in text
        big = report_parts(tmp_path / "big", scenarios=10)
        other = big["cli"].markdown(big["pool"], big["analyses"], big["dry"], None)
        assert "都不触发" in other

    def test_over_cap_warning_is_conditional(self, tmp_path):
        parts = report_parts(tmp_path, estimate=10.9)
        assert "超过 $5 硬上限" in parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        cheap = report_parts(tmp_path / "cheap", estimate=3.2)
        assert "超过 $5 硬上限" not in cheap["cli"].markdown(cheap["pool"], cheap["analyses"], cheap["dry"], None)

    def test_missing_replay_is_not_reported_as_full_coverage(self, tmp_path):
        parts = report_parts(tmp_path, replay=False)
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert "缓存覆盖**未验证**" in text
        assert "缓存未命中 **0**" not in text

    def test_pair_level_and_per_scenario_tables_are_present(self, tmp_path):
        parts = report_parts(tmp_path)
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert "#### 4.1 配对级" in text
        assert "#### 4.3 per-scenario × per-variant" in text
        assert "#### 4.4 fail→pass among baseline-fail" in text
        assert "| scenario0 |" in text
        assert "1/1" in text

    def test_error_counts_in_limitations_come_from_the_replay(self, tmp_path):
        parts = report_parts(tmp_path, error_rows=3)
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        replay = parts["dry"]["replay"]
        expected = (f"防御臂格式失败 {replay['error_rows_by_arm']['defended']}/{replay['rows_by_arm']['defended']}"
                    f" vs 未防御 {replay['error_rows_by_arm']['undefended']}/{replay['rows_by_arm']['undefended']}")
        assert expected in text
        assert "19/864" not in text

    def test_v1_decomposition_appears_only_when_the_ratio_matches(self, tmp_path):
        parts = report_parts(tmp_path)
        analysis = parts["analyses"]["merge"]
        entry = analysis["baseline_fail"]["trajectory_accuracy|raw"]
        entry.update(pairs=24, fail_to_pass_pairs=18, n_traj=1, n_scenario=1, case_study=True,
                     trace_ids=["1503ef20-0000-0000-0000-000000000000"], scenario_ids=["ambiguous_contact_email"])
        text = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert "18/24 配对 = 0.75" in text
        assert "v1 报告的「75% 翻转率」正是这个比值" in text
        assert "1 条轨迹 / 1 个场景" in text
        entry["fail_to_pass_pairs"] = 1
        other = parts["cli"].markdown(parts["pool"], parts["analyses"], parts["dry"], None)
        assert "75% 翻转率" not in other

    def test_informative_cluster_limitation_is_reported(self, tmp_path):
        cli = load_script("phase3_analysis")
        rows, mapping = synth(scenarios=5, arms=(False,), graders=("trajectory_accuracy",))
        for row in rows:
            if row["variant"] != "original" and mapping[row["task_id"]] in ("scenario1", "scenario3"):
                row["score"] = BASE["trajectory_accuracy"]
        analysis = cli.injection_analysis(rows, mapping, resamples=50, seed=0)
        text = cli.markdown({"merge": _pool_stub(), "split": _pool_stub(), "primary_variant": "merge"},
                            {"merge": analysis}, _dry_stub(), None)
        assert "非零均值场景只有 3–3 个" in text
        assert "p 值实际由这几个场景支撑" in text


def _pool_stub():
    return {"candidates": 10, "candidate_tasks": 10, "candidate_scenarios": 5, "selected": 10, "labeled": 10,
            "never_selected": 0, "unlabeled_total": 0, "blank_in_selected": [],
            "human_fail": {"n_traj": 10, "n_scenario": 5, "per_scenario": [], "trace_ids": []},
            "gate_b": {"required_scenarios": 10, "n_scenario": 5, "triggered": True},
            "unlabeled_pool": {"n_traj": 0, "n_scenario": 0, "scenarios_new_to_fail_pool": 0, "trace_ids": []}}


def _dry_stub():
    return {"plan": {"jobs": 1, "completions": 1, "peak_cap_based_estimate_usd": 0.1},
            "new_api_calls": 0, "new_cost_usd": 0.0, "basis": "stub", "replay": None}