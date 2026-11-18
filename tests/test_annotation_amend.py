"""Adjudication must not move the baseline it is measured against.

test-retest kappa compares the ORIGINAL round-1 labels with round 2, so an
amendment that rewrote labels.csv would silently change the gold standard's own
reliability. These tests pin the append-only behaviour, the round-1-only scope and
the batch-after-round-2 gate.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from trajjudge import annotation as kit

ROOT = Path(__file__).parents[1]
NOW = "2026-11-14T00:00:00+00:00"
VIEW = "# Trace B1\n\n### [0] user\n\nask\n\n### [1] assistant\n\nanswer\n"


def labeled_rows(blind="B1", label="fail", round_id="1"):
    return [{"blind_id": blind, "label": label, "reason": "original round-1 reason",
             "annotated_at": "2026-11-01T00:00:00+00:00", "round": round_id}]


@pytest.fixture
def log(tmp_path):
    return tmp_path / "amendments.jsonl"


class TestAmendRecord:
    def test_the_record_keeps_both_values_and_the_decision_context(self, log):
        record = kit.amend_row(log, labeled_rows(), "B1", "pass", "[1] 复核后认为结果正确",
                               criteria_version="criteria-v1", now=NOW, indices=[0, 1])
        assert record["kind"] == "adjudication"
        assert record["round"] == "1"
        assert record["old_label"] == "fail" and record["new_label"] == "pass"
        assert record["old_reason"] == "original round-1 reason"
        assert record["old_annotated_at"] == "2026-11-01T00:00:00+00:00"
        assert record["reason"] == "[1] 复核后认为结果正确"
        assert record["criteria_version"] == "criteria-v1"
        assert record["at"] == NOW
        assert record["blind_id"] == "B1"

    def test_the_label_csv_is_never_rewritten(self, log, tmp_path):
        csv_path = tmp_path / "labels.csv"
        kit.save_labels(csv_path, labeled_rows())
        before = csv_path.read_bytes()
        kit.amend_row(log, kit.read_labels(csv_path), "B1", "pass", "[0] 复核",
                      criteria_version="criteria-v1", now=NOW)
        assert csv_path.read_bytes() == before
        assert kit.read_labels(csv_path)[0]["label"] == "fail"

    def test_two_amendments_both_stay_in_the_log_and_the_last_wins(self, log):
        rows = labeled_rows()
        kit.amend_row(log, rows, "B1", "pass", "[0] 第一次复核", criteria_version="v1", now=NOW)
        kit.amend_row(log, rows, "B1", "fail", "[1] 第二次复核", criteria_version="v2", now=NOW)
        lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert len(lines) == 2
        assert [r["new_label"] for r in lines] == ["pass", "fail"]
        assert [r["criteria_version"] for r in lines] == ["v1", "v2"]
        assert kit.read_amendments(log)["B1"]["new_label"] == "fail"

    def test_a_missing_log_reads_as_no_amendments(self, tmp_path):
        assert kit.read_amendments(tmp_path / "absent.jsonl") == {}

    def test_blank_lines_in_the_log_are_tolerated(self, log):
        kit.amend_row(log, labeled_rows(), "B1", "pass", "[0] 复核", criteria_version="v1", now=NOW)
        log.write_text(log.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
        assert kit.read_amendments(log)["B1"]["new_label"] == "pass"


class TestAmendRefusals:
    def test_a_reason_without_a_message_citation_is_rejected(self, log):
        with pytest.raises(ValueError, match=r"cite at least one message index"):
            kit.amend_row(log, labeled_rows(), "B1", "pass", "复核后认为正确",
                          criteria_version="v1", now=NOW)
        assert not log.exists()

    def test_a_citation_to_a_nonexistent_message_is_rejected(self, log):
        with pytest.raises(ValueError, match=r"do not exist"):
            kit.amend_row(log, labeled_rows(), "B1", "pass", "[9] 复核",
                          criteria_version="v1", now=NOW, indices=[0, 1])
        assert not log.exists()

    def test_an_unknown_label_is_rejected(self, log):
        with pytest.raises(ValueError, match="label must be one of"):
            kit.amend_row(log, labeled_rows(), "B1", "maybe", "[0] 复核",
                          criteria_version="v1", now=NOW)

    def test_a_missing_criteria_version_is_rejected(self, log):
        with pytest.raises(ValueError, match="criteria version"):
            kit.amend_row(log, labeled_rows(), "B1", "pass", "[0] 复核",
                          criteria_version="   ", now=NOW)

    def test_a_blank_round1_row_cannot_be_adjudicated_into_a_label(self, log):
        rows = [{"blind_id": "B1", "label": "", "reason": "", "annotated_at": "", "round": "1"}]
        with pytest.raises(ValueError, match="blank"):
            kit.amend_row(log, rows, "B1", "pass", "[0] 复核", criteria_version="v1", now=NOW)
        assert not log.exists()

    def test_an_unknown_blind_id_is_rejected(self, log):
        with pytest.raises(ValueError, match="no round 1 row"):
            kit.amend_row(log, labeled_rows(), "B9", "pass", "[0] 复核",
                          criteria_version="v1", now=NOW)

    def test_a_round2_row_is_out_of_scope(self, log):
        with pytest.raises(ValueError, match="only applies to round 1"):
            kit.amend_row(log, labeled_rows(blind="R1", round_id="2"), "R1", "pass", "[0] 复核",
                          criteria_version="v1", now=NOW)

    def test_a_round1_id_that_only_exists_in_round2_is_out_of_scope(self, log):
        with pytest.raises(ValueError, match="no round 1 row"):
            kit.amend_row(log, labeled_rows(blind="B1", round_id="2"), "B1", "pass", "[0] 复核",
                          criteria_version="v1", now=NOW)


@pytest.fixture
def cli(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("annotate_cli_amend", ROOT / "scripts/annotate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ann = tmp_path / "annotation"
    (ann / "traces").mkdir(parents=True)
    monkeypatch.setattr(module, "ANN", ann)
    monkeypatch.setattr(module, "CSV_PATH", ann / "labels.csv")
    monkeypatch.setattr(module, "KEY", tmp_path / "key.json")
    module.KEY.write_text(json.dumps({"trace": "B1"}))
    (ann / "traces/B1.md").write_text(VIEW, encoding="utf-8")
    kit.save_labels(module.CSV_PATH, labeled_rows())
    return module


def finish_round2(cli, labels=("pass",), excluded=()):
    rows = [{"blind_id": f"R{k}", "label": label, "reason": "[0] round-2 reason",
             "annotated_at": NOW, "round": "2"} for k, label in enumerate(labels)]
    kit.save_labels(cli.ANN / "round2_labels.csv", rows)
    for blind in excluded:
        kit.append_audit(cli.ANN / "exclusions.jsonl",
                         {"action": "exclude", "blind_id": blind, "round": "2",
                          "reason": "retired", "at": NOW})


class TestAmendCliGate:
    def test_adjudication_is_refused_before_the_round2_kit_exists(self, cli):
        with pytest.raises(SystemExit, match="after round 2"):
            cli.amend("B1", "pass", "[1] 复核", "criteria-v1")
        assert not (cli.ANN / "amendments.jsonl").exists()

    def test_adjudication_is_refused_while_round2_is_partially_labeled(self, cli):
        finish_round2(cli, labels=("pass", ""))
        with pytest.raises(SystemExit, match="after round 2"):
            cli.amend("B1", "pass", "[1] 复核", "criteria-v1")
        assert not (cli.ANN / "amendments.jsonl").exists()

    def test_adjudication_is_refused_when_round2_has_no_rows(self, cli):
        kit.save_labels(cli.ANN / "round2_labels.csv", [])
        with pytest.raises(SystemExit, match="after round 2"):
            cli.amend("B1", "pass", "[1] 复核", "criteria-v1")

    def test_a_retired_round2_row_does_not_block_the_batch_forever(self, cli):
        finish_round2(cli, labels=("pass", ""), excluded=("R1",))
        cli.amend("B1", "pass", "[1] 复核", "criteria-v1")
        assert kit.read_amendments(cli.ANN / "amendments.jsonl")["B1"]["new_label"] == "pass"

    def test_an_excluded_round1_item_must_be_reinstated_first(self, cli):
        finish_round2(cli)
        kit.append_audit(cli.ANN / "exclusions.jsonl",
                         {"action": "exclude", "blind_id": "B1", "round": "1",
                          "reason": "retired", "at": NOW})
        with pytest.raises(SystemExit, match="reinstate"):
            cli.amend("B1", "pass", "[1] 复核", "criteria-v1")
        assert not (cli.ANN / "amendments.jsonl").exists()

    def test_the_citation_is_checked_against_the_rendered_round1_view(self, cli):
        finish_round2(cli)
        with pytest.raises(SystemExit, match="do not exist"):
            cli.amend("B1", "pass", "[7] 复核", "criteria-v1")
        assert not (cli.ANN / "amendments.jsonl").exists()


class TestAmendCliEffects:
    def test_a_successful_amendment_leaves_round1_and_round2_byte_identical(self, cli, capsys):
        finish_round2(cli)
        first = cli.CSV_PATH.read_bytes()
        second = (cli.ANN / "round2_labels.csv").read_bytes()
        cli.amend("B1", "pass", "[1] 复核后改判", "criteria-v1")
        assert cli.CSV_PATH.read_bytes() == first
        assert (cli.ANN / "round2_labels.csv").read_bytes() == second
        out = capsys.readouterr().out
        assert "fail -> pass" in out and "criteria-v1" in out
        assert "unchanged" in out and "no metrics recomputed" in out

    def test_amendments_do_not_disturb_the_exclusion_state(self, cli):
        finish_round2(cli)
        kit.append_audit(cli.ANN / "exclusions.jsonl",
                         {"action": "exclude", "blind_id": "B2", "round": "1",
                          "reason": "retired", "at": NOW})
        cli.amend("B1", "pass", "[1] 复核", "criteria-v1")
        assert ("B2", "1") in kit.read_exclusions(cli.ANN / "exclusions.jsonl")
        assert kit.read_amendments(cli.ANN / "amendments.jsonl").keys() == {"B1"}

    def test_amend_writes_only_the_audit_log(self, cli):
        finish_round2(cli)
        before = {p.relative_to(cli.ANN) for p in cli.ANN.rglob("*")}
        cli.amend("B1", "pass", "[1] 复核", "criteria-v1")
        after = {p.relative_to(cli.ANN) for p in cli.ANN.rglob("*")}
        assert after - before == {Path("amendments.jsonl")}

    def test_the_audit_log_stays_out_of_the_repository(self):
        assert "annotation/amendments.jsonl" in (ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_the_cli_exposes_amend_with_a_required_criteria_version(self):
        text = (ROOT / "scripts/annotate.py").read_text(encoding="utf-8")
        assert '"amend"' in text
        assert '"--criteria-version", required=True' in text
        assert '"--label", required=True, choices=kit.LABELS' in text