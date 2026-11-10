"""Report joins and cost accounting use synthetic verdicts, never human labels."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from trajjudge.usage import UsageLog, UsageRecord

FIXTURES = Path(__file__).parent / "fixtures" / "claw_s5"
NAMES = ("trajectory_accuracy", "trajectory_comprehensive", "action_loop_detection", "observation_information_gain")


@pytest.fixture
def evidence(tmp_path: Path) -> dict[str, Path]:
    """Make a portable small evidence tree with explicitly synthetic judge scores."""
    target = tmp_path / "outputs" / "claw_eval" / "s5"
    target.mkdir(parents=True)
    tasks: list[dict[str, Any]] = []
    grades: list[dict[str, Any]] = []
    usage: list[UsageRecord] = []
    for name, task_id, score in (("contact", "T010_contact_lookup", 0.804), ("email", "T002_email_triage", 0.85)):
        trace = target / f"{name}.jsonl"
        shutil.copyfile(FIXTURES / f"{name}.jsonl", trace)
        tasks.append({"task_id": task_id, "trial": {"trace": str(trace), "task_score": score}})
        for index, grader in enumerate(NAMES):
            grades.append({"trace_id": f"trace-{name}", "grader": grader, "score": 2 if index == 0 else 0.75,
                           "reason": "Synthetic mock verdict", "judge_model": "judge-test" if index < 2 else None,
                           "thinking": False if index < 2 else None, "openjudge_commit": "a" * 40,
                           "timestamp": "2026-11-04T00:00:00+00:00", "status": "ok",
                           "usage": {"prompt_tokens": 100 if index < 2 else 0, "completion_tokens": 30 if index < 2 else 0,
                                     "api_calls": 0, "cached_calls": 1 if index < 2 else 0},
                           "metadata": {"task_id": task_id, "official_result": {"task_score": score}}})
            if index < 2:
                usage.append(UsageRecord("2026-11-04T00:00:00+00:00", f"s6/trace-{name}/{grader}", "judge-test", False, 100, 30, 1, False))
    usage.extend([
        UsageRecord("2026-11-04T00:00:00+00:00", "s2/plain", "judge-test", False, 10, 2, 1, False),
        UsageRecord("2026-11-04T00:00:00+00:00", "s5/T010_contact_lookup/agent", "judge-test", False, 100, 10, 1, False),
        UsageRecord("2026-11-04T00:00:00+00:00", "s5/T010_contact_lookup/judge", "judge-test", True, 50, 5, 1, False),
    ])
    manifest = target / "pilot.json"
    manifest.write_text(json.dumps({"status": "complete", "tasks": tasks, "claw_eval_commit": "b" * 40,
                                   "deviations": ["Synthetic runtime difference for report test"]}))
    scores = tmp_path / "outputs" / "scores.jsonl"
    scores.write_text("".join(json.dumps(row) + "\n" for row in grades))
    ledger = tmp_path / "outputs" / "usage.jsonl"
    for row in usage:
        UsageLog(ledger).append(row)
        UsageLog(ledger).append(replace(row, cached=True))
    price = tmp_path / "prices.yaml"
    price.write_text("models:\n  judge-test:\n    input_per_mtok: 1\n    output_per_mtok: 2\n")
    return {"pilot_path": manifest, "scores_path": scores, "usage_path": ledger, "pricing_path": price,
            "output_path": tmp_path / "reports" / "phase1.md", "project_root": tmp_path}


def test_join_and_cost_ignore_cached_logical_tokens(evidence: dict[str, Path]) -> None:
    from trajjudge.reporting import generate_report
    result = generate_report(**evidence)
    assert result.complete
    assert "$0.000834" in result.markdown
    assert "560" in result.markdown and "137" in result.markdown
    rows = [line for line in result.markdown.splitlines() if line.startswith("| T0")]
    assert len(rows) == 2
    assert "0.804000" in rows[0] and "2.000000" in rows[0]
    assert "0.850000" in rows[1]
    assert "1–3" in result.markdown and "0–1" in result.markdown
    assert "not leaderboard" in result.markdown.lower()


def test_regeneration_is_deterministic_despite_replays(evidence: dict[str, Path]) -> None:
    from trajjudge.reporting import generate_report
    first = generate_report(**evidence).markdown
    original = UsageLog(evidence["usage_path"]).read()[0]
    UsageLog(evidence["usage_path"]).append(replace(original, cached=True, timestamp="2030-01-01T00:00:00+00:00"))
    assert generate_report(**evidence).markdown == first
    assert evidence["output_path"].read_text() == first


@pytest.mark.parametrize("failure", ["missing", "error", "invalid_score"])
def test_failed_or_missing_verdict_stays_in_denominator(evidence: dict[str, Path], failure: str) -> None:
    from trajjudge.reporting import generate_report
    rows = [json.loads(line) for line in evidence["scores_path"].read_text().splitlines()]
    if failure == "missing":
        rows.pop(0)
    elif failure == "error":
        rows[0].update(status="error", score=None)
    else:
        rows[0]["score"] = 99
    evidence["scores_path"].write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = generate_report(**evidence)
    assert not result.complete
    assert "MISSING" in result.markdown or "ERROR" in result.markdown
    assert len([line for line in result.markdown.splitlines() if line.startswith("| T0")]) == 2


@pytest.mark.parametrize("failure", ["duplicate", "foreign_trace", "wrong_task", "wrong_framework_score"])
def test_ambiguous_or_mismatched_rows_are_rejected(evidence: dict[str, Path], failure: str) -> None:
    from trajjudge.reporting import generate_report
    rows = [json.loads(line) for line in evidence["scores_path"].read_text().splitlines()]
    if failure == "duplicate":
        rows.append(rows[0])
    elif failure == "foreign_trace":
        rows[0]["trace_id"] = "foreign"
    elif failure == "wrong_task":
        rows[0]["metadata"]["task_id"] = "foreign"
    else:
        rows[0]["metadata"]["official_result"]["task_score"] = 0.1
    evidence["scores_path"].write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        generate_report(**evidence)
    assert not evidence["output_path"].exists()


def test_missing_ledger_never_becomes_zero_spend(evidence: dict[str, Path]) -> None:
    from trajjudge.reporting import generate_report
    evidence["usage_path"].unlink()
    with pytest.raises(ValueError, match="ledger"):
        generate_report(**evidence)


def test_unknown_prices_are_visible_and_incomplete(evidence: dict[str, Path]) -> None:
    from trajjudge.reporting import generate_report
    evidence["pricing_path"].write_text("models: {}\n")
    result = generate_report(**evidence)
    assert not result.complete and "UNKNOWN" in result.markdown


def test_pending_accounting_cannot_look_complete(evidence: dict[str, Path]) -> None:
    from trajjudge.reporting import generate_report
    evidence["usage_path"].with_suffix(".pending").write_text("Synthetic unreconciled request")
    result = generate_report(**evidence)
    assert not result.complete and "UNKNOWN" in result.markdown


def test_relocated_manifest_uses_current_tree(evidence: dict[str, Path]) -> None:
    from trajjudge.reporting import generate_report
    manifest = json.loads(evidence["pilot_path"].read_text())
    for task in manifest["tasks"]:
        relative = Path(task["trial"]["trace"]).relative_to(evidence["project_root"])
        task["trial"]["trace"] = str(Path("/old/nonexistent/project") / relative)
    evidence["pilot_path"].write_text(json.dumps(manifest))
    assert generate_report(**evidence).complete


@pytest.mark.parametrize("failure", ["model", "thinking", "all_thinking_on", "unmatched_model"])
def test_conflicting_or_unbilled_model_provenance_is_rejected(evidence: dict[str, Path], failure: str) -> None:
    from trajjudge.reporting import generate_report
    rows = [json.loads(line) for line in evidence["scores_path"].read_text().splitlines()]
    if failure in {"model", "thinking"}:
        rows[0]["judge_model" if failure == "model" else "thinking"] = "foreign-model" if failure == "model" else True
    else:
        for row in rows:
            if row["judge_model"] is not None:
                row["thinking" if failure == "all_thinking_on" else "judge_model"] = True if failure == "all_thinking_on" else "foreign-model"
    evidence["scores_path"].write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        generate_report(**evidence)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_scores_write_an_incomplete_report(evidence: dict[str, Path], score: float) -> None:
    from trajjudge.reporting import generate_report
    rows = [json.loads(line) for line in evidence["scores_path"].read_text().splitlines()]
    rows[0]["score"] = score
    evidence["scores_path"].write_text("".join(json.dumps(row) + "\n" for row in rows))
    result = generate_report(**evidence)
    assert not result.complete and "ERROR" in result.markdown
    assert evidence["output_path"].read_text() == result.markdown
