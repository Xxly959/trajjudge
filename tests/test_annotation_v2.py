"""Phase 2: exclusion audit, round-2 blindness and evidence-bound reasons. No real labels."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from annotation_env import build_env, resolve_blanks
from trajjudge import annotation as kit


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return build_env(tmp_path, monkeypatch)


def test_exclude_requires_reason_and_keeps_the_csv_row(env) -> None:
    cli, blank = env["cli"], env["rows"][8]["blind_id"]
    with pytest.raises(ValueError, match="reason"):
        kit.exclude_row(cli._exclusions(), env["rows"], blank, "   ", now="t")
    kit.exclude_row(cli._exclusions(), env["rows"], blank, "cannot decide", now="t")
    assert cli._exclusions().read_text().count("\n") == 1
    assert blank in {r["blind_id"] for r in kit.read_labels(cli.CSV_PATH)}


def test_exclude_refuses_a_labeled_row(env) -> None:
    with pytest.raises(ValueError, match="already carries a label"):
        kit.exclude_row(env["cli"]._exclusions(), env["rows"], env["rows"][0]["blind_id"], "x", now="t")
    assert not env["cli"]._exclusions().exists()


def test_exclude_refuses_unknown_id_and_double_exclusion(env) -> None:
    cli, blank = env["cli"], env["rows"][8]["blind_id"]
    with pytest.raises(ValueError, match="no round 1 row"):
        kit.exclude_row(cli._exclusions(), env["rows"], "Bnope", "x", now="t")
    kit.exclude_row(cli._exclusions(), env["rows"], blank, "x", now="t")
    with pytest.raises(ValueError, match="already excluded"):
        kit.exclude_row(cli._exclusions(), env["rows"], blank, "y", now="t")


def test_reinstate_keeps_both_audit_records(env) -> None:
    cli, blank = env["cli"], env["rows"][8]["blind_id"]
    kit.exclude_row(cli._exclusions(), env["rows"], blank, "cannot decide", now="t1")
    with pytest.raises(ValueError, match="reason"):
        kit.reinstate_row(cli._exclusions(), blank, "", now="t2")
    kit.reinstate_row(cli._exclusions(), blank, "new evidence arrived", now="t2")
    records = [json.loads(line) for line in cli._exclusions().read_text().splitlines()]
    assert [r["action"] for r in records] == ["exclude", "reinstate"]
    assert kit.read_exclusions(cli._exclusions()) == {}
    with pytest.raises(ValueError, match="not excluded"):
        kit.reinstate_row(cli._exclusions(), blank, "again", now="t3")


def test_labeling_an_excluded_row_is_reported(env) -> None:
    cli, blank = env["cli"], env["rows"][8]["blind_id"]
    kit.exclude_row(cli._exclusions(), env["rows"], blank, "cannot decide", now="t")
    rows = kit.read_labels(cli.CSV_PATH)
    expected = sorted(env["mapping"].values())
    assert kit.validate_labels(rows, expected, excluded=[(blank, "1")]) == []
    next(r for r in rows if r["blind_id"] == blank).update(label="pass", reason="smuggled back in")
    problems = kit.validate_labels(rows, expected, excluded=[(blank, "1")])
    assert any("excluded row carries a label" in p for p in problems)


def test_explicit_exclusion_unblocks_the_relabel_deadlock(env) -> None:
    cli = env["cli"]
    with pytest.raises(SystemExit, match="unresolved"):
        cli.relabel(4)
    resolve_blanks(env)
    cli.relabel(4)
    second = [r for r in kit.read_labels(cli.CSV_PATH) if r["round"] == "2"]
    assert len(second) == 4 and all(r["label"] == r["reason"] == "" for r in second)
    assert {r["blind_id"] for r in second}.isdisjoint(env["mapping"].values())


def test_round2_requires_the_two_day_gap(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    rows = kit.read_labels(cli.CSV_PATH)
    for row in rows:
        if row["label"]:
            row["annotated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    kit.save_labels(cli.CSV_PATH, rows)
    with pytest.raises(SystemExit, match="two days"):
        cli.round2(None)
    assert not cli._round2_csv().exists()


def test_round2_kit_is_blank_fresh_and_separate(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(None)
    rows = kit.read_labels(cli._round2_csv())
    assert len(rows) == 8
    assert all(r["round"] == "2" and r["label"] == "" and r["reason"] == "" and r["annotated_at"] == "" for r in rows)
    fresh = {r["blind_id"] for r in rows}
    assert len(fresh) == 8 and fresh.isdisjoint(env["mapping"].values())
    assert all(f.startswith("R") for f in fresh)
    assert set(json.loads(cli._round2_key().read_text())) == fresh
    assert kit.read_labels(cli.CSV_PATH) == env["rows"]


def test_round2_views_hide_round1_ids_labels_and_scores(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(None)
    reasons = {r["reason"] for r in env["rows"] if r["reason"]}
    for fresh, blind in json.loads(cli._round2_key().read_text()).items():
        text = (cli.ANN / "round2" / "traces" / f"{fresh}.md").read_text(encoding="utf-8")
        assert f"# Trace {fresh}" in text
        assert blind not in text and "trace-contact" not in text.lower()
        assert "score" not in text.lower() and "deepseek" not in text.lower()
        assert not any(reason in text for reason in reasons)
        assert "### [0]" in text and "## Task criteria" in text


def test_round2_guide_has_two_pass_two_fail_examples_and_no_grader_output(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(None)
    guide = (cli.ANN / "GUIDE.md").read_text(encoding="utf-8")
    assert guide.count("**pass 例") == 2 and guide.count("**fail 例") == 2
    assert "虚构演示" in guide and "[3]" in guide
    for forbidden in ("kappa", "κ=", "deepseek", "trajectory_accuracy", "0.377", "评分器输出："):
        assert forbidden not in guide.lower()


def test_round2_refuses_to_overwrite_an_existing_kit(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(None)
    before = cli._round2_csv().read_bytes()
    with pytest.raises(SystemExit, match="already exists"):
        cli.round2(None)
    assert cli._round2_csv().read_bytes() == before


def test_round2_refuses_evidence_whose_hash_changed(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    Path(env["items"][0]["trace"]).write_text("tampered\n")
    with pytest.raises(SystemExit, match="frozen annotation evidence changed"):
        cli.round2(None)


def test_round2_count_selects_exactly_that_many_labeled_rows(env) -> None:
    """The sample must be drawn once; re-drawing per row silently selects the wrong size."""
    cli = env["cli"]
    resolve_blanks(env)
    labeled = {r["blind_id"] for r in env["rows"] if r["label"]}
    for count in (1, 3, 5, 8, 99):
        child = env["tmp"] / f"subset{count}"
        child.mkdir()
        cli.ANN = child / "annotation"
        (cli.ANN / "traces").mkdir(parents=True)
        shutil.copyfile(env["ann"] / "exclusions.jsonl", cli.ANN / "exclusions.jsonl")
        for blind in labeled:
            (cli.ANN / "traces" / f"{blind}.md").write_text(
                (env["ann"] / "traces" / f"{blind}.md").read_text(encoding="utf-8"), encoding="utf-8")
        cli.KEY = child / "key.json"
        cli.KEY.write_text(json.dumps(env["mapping"]))
        cli.round2(count)
        rows = kit.read_labels(cli._round2_csv())
        assert len(rows) == min(count, len(labeled))
        key = json.loads(cli._round2_key().read_text())
        assert len(key) == len(rows) and set(key.values()) <= labeled


def test_round2_refuses_an_empty_kit(env) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    with pytest.raises(SystemExit, match="at least 1"):
        cli.round2(0)
    assert not cli._round2_csv().exists()


def test_check_warns_about_terse_reasons_without_rejecting_them(env, capsys) -> None:
    cli = env["cli"]
    rows = kit.read_labels(cli.CSV_PATH)
    rows[0].update(reason="正确")
    kit.save_labels(cli.CSV_PATH, rows)
    cli.check()
    out = capsys.readouterr().out
    assert "reason quality warnings (advisory" in out and "generic phrase" in out
    assert "problems: none" in out
    assert kit.read_labels(cli.CSV_PATH)[0]["label"] == rows[0]["label"]


def _answer(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    stream = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(stream))


def test_round2_label_rejects_a_reason_without_a_citation(env, monkeypatch) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(1)
    fresh = kit.read_labels(cli._round2_csv())[0]["blind_id"]
    _answer(monkeypatch, ["p", "looks fine to me", "[999] out of range", "[2] tool result supports the claim"])
    cli.label("2", cli._round2_csv())
    row = kit.read_labels(cli._round2_csv())[0]
    assert row["blind_id"] == fresh and row["label"] == "pass"
    assert row["reason"] == "[2] tool result supports the claim"
    assert row["round"] == "2" and row["annotated_at"]


def test_round1_label_does_not_require_a_citation(env, monkeypatch) -> None:
    cli = env["cli"]
    blank = env["rows"][8]["blind_id"]
    _answer(monkeypatch, ["f", "no citation needed in round 1", "q"])
    cli.label("1")
    row = next(r for r in kit.read_labels(cli.CSV_PATH) if r["blind_id"] == blank)
    assert row["label"] == "fail" and row["reason"] == "no citation needed in round 1"


def test_check_reports_round2_progress_and_citation_problems(env, capsys) -> None:
    cli = env["cli"]
    resolve_blanks(env)
    cli.round2(2)
    rows = kit.read_labels(cli._round2_csv())
    rows[0].update(label="pass", reason="no index here", annotated_at="2026-11-13T00:00:00+00:00")
    kit.save_labels(cli._round2_csv(), rows)
    cli.check()
    out = capsys.readouterr().out
    assert "round 2: 1/2 labeled" in out
    assert "must cite at least one message index" in out