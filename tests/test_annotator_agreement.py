"""Phase 2: test-retest agreement, the frozen kappa verdict and gate A. Synthetic labels only."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from annotation_env import build_env, load_script, resolve_blanks
from trajjudge import annotation as kit

agreement = load_script("annotator_agreement")


def _row(blind: str, label: str, round_id: str = "1", stamp: str = "") -> dict:
    return {"blind_id": blind, "label": label, "reason": f"synthetic {blind}", "annotated_at": stamp, "round": round_id}


def _pairs(*specs: tuple[str, str, str]) -> list[dict]:
    return [{"round1_blind_id": b, "round2_blind_id": f"R{b}", "round1": x, "round2": y} for b, x, y in specs]


def test_pair_rounds_reports_every_unpaired_reason() -> None:
    round1 = [_row("B1", "pass"), _row("B2", ""), _row("B3", "fail"), _row("B4", "pass"), _row("B5", "pass")]
    round2 = [_row("Ra", "pass", "2"), _row("Rb", "", "2"), _row("Rc", "fail", "2"), _row("Rd", "pass", "2")]
    key = {"Ra": "B1", "Rb": "B2", "Rc": "B3", "Rd": "B4", "Re": "B5", "Rf": "Bgone"}
    pairs, unpaired = agreement.pair_rounds(round1, round2, key, excluded=[("B4", "1"), ("Rc", "2")])
    assert [p["round1_blind_id"] for p in pairs] == ["B1"]
    reasons = {u["round1_blind_id"]: u["reason"] for u in unpaired}
    assert reasons == {"B2": "round 1 blank", "B3": "round 2 excluded", "B4": "round 1 excluded",
                       "B5": "round 2 row missing", "Bgone": "round 1 row missing"}


def test_unselected_round1_rows_are_counted_not_dropped() -> None:
    round1 = [_row("B1", "pass"), _row("B2", "fail")]
    pairs, unpaired = agreement.pair_rounds(round1, [_row("Ra", "pass", "2")], {"Ra": "B1"})
    assert len(pairs) == 1
    assert unpaired == [{"round1_blind_id": "B2", "round2_blind_id": None, "reason": "not selected for round 2"}]


def test_known_kappa_and_transitions() -> None:
    pairs = _pairs(("B1", "pass", "pass"), ("B2", "pass", "pass"), ("B3", "pass", "fail"), ("B4", "fail", "fail"))
    units = {f"B{i}": f"s{i}" for i in range(1, 5)}
    stats = agreement.agreement_stats(pairs, units, resamples=200, seed=0)
    assert stats["raw_agreement"] == 0.75
    assert stats["kappa"] == pytest.approx(0.5)
    assert stats["pabak"] == pytest.approx(0.5)
    assert stats["transitions"] == {"pass_to_pass": 2, "pass_to_fail": 1, "fail_to_pass": 0, "fail_to_fail": 1}
    assert stats["changed"] == 1 and stats["n_paired"] == 4


def test_fewer_than_five_scenarios_is_a_case_study() -> None:
    pairs = _pairs(("B1", "pass", "pass"), ("B2", "pass", "fail"), ("B3", "fail", "fail"), ("B4", "fail", "pass"))
    stats = agreement.agreement_stats(pairs, {f"B{i}": f"s{i}" for i in range(1, 5)}, resamples=200)
    assert stats["case_study"] is True and stats["n_scenario_paired"] == 4
    many = _pairs(*[(f"B{i}", "pass" if i % 2 else "fail", "pass" if i % 3 else "fail") for i in range(10)])
    stats = agreement.agreement_stats(many, {f"B{i}": f"s{i // 2}" for i in range(10)}, resamples=200)
    assert stats["case_study"] is False and stats["n_scenario_paired"] == 5


def test_translation_twins_share_one_cluster() -> None:
    pairs = _pairs(*[(f"B{i}", "pass" if i % 2 else "fail", "pass" if i % 3 else "fail") for i in range(10)])
    blind = [f"B{i}" for i in range(10)]
    stats = agreement.agreement_stats(pairs, dict(zip(blind, [f"s{i // 2}" for i in range(10)])),
                                      task_units=dict(zip(blind, [f"t{i}" for i in range(10)])), resamples=200)
    assert stats["intervals"]["clusters"] == 5 and stats["intervals"]["cluster_unit"] == "scenario_id"
    assert stats["task_id_intervals"]["clusters"] == 10 and stats["task_id_intervals"]["cluster_unit"] == "task_id"


def test_degenerate_labels_report_undefined_draws_and_no_zero_width_ci() -> None:
    pairs = _pairs(*[(f"B{i}", "pass", "pass") for i in range(6)])
    stats = agreement.agreement_stats(pairs, {f"B{i}": f"s{i}" for i in range(6)}, resamples=200)
    kappa = stats["intervals"]["kappa"]
    assert kappa["undefined_draws"] == 200 and kappa["undefined_share"] == 1.0
    assert kappa["ci"] is None and kappa["status"] == "not_estimable"
    assert stats["intervals"]["raw_agreement"]["ci"] is None


def test_verdict_below_threshold_downgrades_grader_metrics() -> None:
    stats = {"n_paired": 8, "kappa": 0.42, "intervals": {"kappa": {"ci": [0.1, 0.7], "status": "ok"}}}
    verdict = agreement.stability_verdict(stats)
    assert verdict["status"] == "unstable" and verdict["gold_standard_unstable"] is True
    assert "降级为 exploratory" in verdict["statement"]


def test_verdict_above_threshold_with_low_ci_is_only_unconfirmed() -> None:
    stats = {"n_paired": 8, "kappa": 0.7, "intervals": {"kappa": {"ci": [0.4, 0.9], "status": "ok"}}}
    verdict = agreement.stability_verdict(stats)
    assert verdict["status"] == "unconfirmed" and verdict["gold_standard_unstable"] is False
    assert "稳定性未确证" in verdict["statement"]
    stable = agreement.stability_verdict({"n_paired": 8, "kappa": 0.8,
                                          "intervals": {"kappa": {"ci": [0.65, 0.95], "status": "ok"}}})
    assert stable["status"] == "stable"


def test_verdict_never_substitutes_a_point_estimate_for_an_unestimable_ci() -> None:
    verdict = agreement.stability_verdict({"n_paired": 8, "kappa": 0.9,
                                           "intervals": {"kappa": {"ci": None, "status": "not_estimable",
                                                                   "reason": "不可估（簇数不足）"}}})
    assert verdict["status"] == "not_estimable" and verdict["gold_standard_unstable"] is None
    assert "无法判定" in verdict["statement"]


def test_verdict_is_blocked_without_pairs() -> None:
    verdict = agreement.stability_verdict({"n_paired": 0})
    assert verdict["status"] == "blocked" and "闸门 A" in verdict["statement"]


def _stamp(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def test_gate_requires_resolution_completion_and_gap() -> None:
    round1 = [_row("B1", "pass", stamp=_stamp(4)), _row("B2", "")]
    key = {"Ra": "B1"}
    round2 = [_row("Ra", "", "2")]
    gate = agreement.gate_status(round1, round2, key, {})
    assert gate["ready"] is False and any("exclude" in a for a in gate["actions"])
    resolved = agreement.gate_status(round1, round2, key, {("B2", "1"): {}})
    assert resolved["ready"] is False and any("label --round 2" in a for a in resolved["actions"])
    done = [_row("Ra", "pass", "2")]
    assert agreement.gate_status(round1, done, key, {("B2", "1"): {}})["ready"] is True
    recent = [_row("B1", "pass", stamp=_stamp(0.02)), _row("B2", "")]
    late = agreement.gate_status(recent, done, key, {("B2", "1"): {}})
    assert late["ready"] is False and any("48h" in a for a in late["actions"])
    assert agreement.gate_status(round1, [], {}, {})["ready"] is False


def test_absent_second_annotator_is_stated_not_implied() -> None:
    out = agreement.second_annotator([], [_row("B1", "pass")], {"B1": "s1"}, resamples=50, seed=0)
    assert out["available"] is False and "无法计算 inter-annotator" in out["statement"]


def test_second_annotator_uses_shared_blind_ids() -> None:
    round1 = [_row("B1", "pass"), _row("B2", "fail"), _row("B3", "")]
    second = [_row("B1", "pass"), _row("B2", "pass"), _row("B3", "fail"), _row("B9", "pass")]
    out = agreement.second_annotator(second, round1, {"B1": "s1", "B2": "s2"}, resamples=50, seed=0)
    assert out["available"] is True and out["n_paired"] == 2
    assert out["raw_agreement"] == 0.5 and out["kappa"] == pytest.approx(0.0)


def test_grader_comparison_puts_both_raters_side_by_side(tmp_path: Path) -> None:
    report = tmp_path / "p2-v2.json"
    report.write_text(json.dumps({"agreement": {
        "official_vs_human": {"n": 48, "kappa": 0.377, "kappa_ci": [0.09, 0.69], "accuracy": 0.77},
        "graders": {"trajectory_accuracy": {"n": 48, "kappa": 0.04, "kappa_ci": [0.0, 0.145], "auc": 0.546},
                    "trajectory_comprehensive": {"n": 48, "kappa": 0.0, "kappa_ci": None, "auc": 0.675}}}}))
    human = {"kappa": 0.42, "intervals": {"kappa": {"ci": [0.1, 0.7]}}}
    out = agreement.grader_comparison(report, human, {"gold_standard_unstable": True})
    assert out["human_test_retest_kappa"] == 0.42 and out["human_kappa_ci"] == [0.1, 0.7]
    assert set(out["raters"]) == {"trajectory_accuracy", "trajectory_comprehensive", "framework_rubric"}
    assert out["grader_metrics_downgraded"] is True
    assert agreement.grader_comparison(tmp_path / "missing.json", human, {})["available"] is False


def test_task_id_comes_from_the_frozen_path_not_the_private_strata(tmp_path: Path) -> None:
    item = {"trace": str(tmp_path / "T026_ambiguous_contact_email_5f925b00.jsonl")}
    assert agreement.task_of(item) == "T026_ambiguous_contact_email"


def test_incomplete_scenario_map_is_an_error(tmp_path: Path) -> None:
    frozen = tmp_path / "set.json"
    frozen.write_text(json.dumps([{"trace_id": "t1", "trace": str(tmp_path / "T001_demo_00000001.jsonl")}]))
    mapping = tmp_path / "map.csv"
    mapping.write_text("task_id,scenario_id\nT999_other,s9\n")
    with pytest.raises(ValueError, match="scenario map missing task_id T001_demo"):
        agreement.scenario_index(frozen, mapping)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return build_env(tmp_path, monkeypatch)


def _argv(env, output: Path, **extra) -> list[str]:
    argv = ["annotator_agreement.py", "--round1", str(env["cli"].CSV_PATH),
            "--round2", str(env["cli"]._round2_csv()), "--round2-key", str(env["cli"]._round2_key()),
            "--key", str(env["cli"].KEY), "--set", str(env["frozen"]),
            "--scenario-map", str(env["scenarios"]), "--exclusions", str(env["cli"]._exclusions()),
            "--grader-report", str(env["tmp"] / "no-grader-report.json"),
            "--resamples", "200", "--output", str(output)]
    for flag, value in extra.items():
        argv += [f"--{flag.replace('_', '-')}", str(value)]
    return argv


def test_main_blocks_at_gate_a_and_writes_no_label_statistic(env, monkeypatch, capsys) -> None:
    output = env["tmp"] / "agreement.json"
    monkeypatch.setattr("sys.argv", _argv(env, output))
    assert agreement.main() == 0
    result = json.loads(output.read_text())
    assert result["status"] == "blocked" and result["test_retest"] is None
    assert result["verdict"]["status"] == "blocked"
    assert "闸门 A 未通过" in capsys.readouterr().out
    assert result["second_annotator"]["statement"] == "单标注者，无 inter-annotator 一致度"


def test_main_reports_agreement_once_the_gate_is_passed(env, monkeypatch, capsys) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(None)
    rows = kit.read_labels(cli._round2_csv())
    for index, row in enumerate(rows):
        row.update(label="pass" if index % 3 else "fail", reason=f"[2] synthetic fixture reason {index}",
                   annotated_at=_stamp(0))
    kit.save_labels(cli._round2_csv(), rows)
    output = env["tmp"] / "agreement.json"
    monkeypatch.setattr("sys.argv", _argv(env, output))
    assert agreement.main() == 0
    result = json.loads(output.read_text())
    assert result["status"] == "ok" and result["gate"]["ready"] is True
    stats = result["test_retest"]
    assert stats["n_paired"] == 8
    assert stats["intervals"]["clusters"] == stats["n_scenario_paired"] <= 5
    assert stats["case_study"] == (stats["n_scenario_paired"] < 5)
    assert stats["task_id_intervals"]["clusters"] == 8
    assert result["coverage"] == {"n_paired": 8, "n_round2_selected": 8, "n_unpaired": 2}
    assert result["verdict"]["status"] in {"unstable", "unconfirmed", "stable", "not_estimable"}
    assert "判定:" in capsys.readouterr().out