import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return runpy.run_path(str(ROOT / "scripts/build_training_candidates.py"))


def test_task_family_cannot_cross_train_and_eval(api):
    with pytest.raises(ValueError, match="task family"):
        api["partition_index"]({"version": 1, "families": [
            {"family": "original:events", "purpose": "train", "tasks": ["events-v1"]},
            {"family": "original:events", "purpose": "eval", "tasks": ["events-v2"]},
        ]})


def example(source, status, *, output="result", context="environment"):
    return {
        "source_id": source, "task": "example", "family": "original:example", "purpose": "train",
        "task_version": 1, "instruction_sha256": "i", "environment_sha256": context, "verifier_version": "v",
        "outcome": status, "reason": "artifact_mismatch" if status == "fail" else "passed_all_checks",
        "messages": [
            {"role": "user", "content": "Create result.json."},
            {"role": "assistant", "tool_calls": [
                {"id": "call-1", "type": "function", "function": {"name": "inspect", "arguments": {"path": "result.json"}}},
            ]},
            {"role": "tool", "tool_call_id": "call-1", "name": "inspect", "content": output},
            {"role": "assistant", "content": f"Observed {output}."},
        ],
        "tools": [{"type": "function", "function": {
            "name": "inspect", "description": "Read a fixture.", "parameters": {
                "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"],
            },
        }}],
    }


def test_preference_requires_same_task_environment_and_different_verified_outcomes(api):
    good = example("a", "pass", output="expected")
    bad = example("b", "fail", output="wrong")
    valid, reason = api["preference_pair"](good, bad)
    assert reason is None
    assert valid["prompt"] == good["messages"][:1]
    assert valid["chosen"] == good["messages"][1:]
    assert valid["rejected"] == bad["messages"][1:]
    for changed, expected in [
        (dict(bad, task="different"), "different_task"),
        (dict(bad, environment_sha256="different"), "different_environment"),
        (dict(bad, purpose="eval"), "evaluation_family"),
        (dict(bad, outcome="pass"), "incomparable_outcomes"),
        (dict(bad, outcome="unknown"), "incomparable_outcomes"),
        (dict(bad, tools=[]), "different_prompt_or_tools"),
        (dict(bad, messages=good["messages"]), "identical_completions"),
    ]:
        assert api["preference_pair"](good, changed) == (None, expected)


def test_tool_link_and_argument_structure_are_required(api):
    item = example("a", "pass")
    api["validate_conversation"](item["messages"], item["tools"])
    malformed = json.loads(json.dumps(item["messages"]))
    malformed[2]["tool_call_id"] = "wrong-id"
    with pytest.raises(ValueError, match="tool return"):
        api["validate_conversation"](malformed, item["tools"])
    malformed = json.loads(json.dumps(item["messages"]))
    malformed[1]["tool_calls"][0]["function"]["arguments"] = '{"path":"result.json"}'
    with pytest.raises(ValueError, match="arguments"):
        api["validate_conversation"](malformed, item["tools"])
    malformed[1]["tool_calls"][0]["function"]["arguments"] = {}
    with pytest.raises(ValueError, match="required"):
        api["validate_conversation"](malformed, item["tools"])
    with pytest.raises(ValueError, match="final"):
        api["validate_conversation"](item["messages"][:-1], item["tools"])


def test_claim_only_comparison_reports_same_denominator(api):
    rows = [
        {"source_id": "claim", "final_reply": "已完成修改并生成 result.json。", "outcome": "fail"},
        {"source_id": "reference", "final_reply": None, "outcome": "pass"},
        {"source_id": "infra", "final_reply": None, "outcome": "unknown"},
    ]
    result = api["compare_filters"](rows)
    assert result["denominator"] == 3
    assert result["final_reply_only"]["selected"] == ["claim"]
    assert result["verified_outcome"]["selected"] == ["reference"]
    assert result["final_reply_only"]["excluded_by_reason"] == {"missing_final_reply": 2}
    assert result["verified_outcome"]["excluded_by_reason"] == {"not_verified_pass": 1, "outcome_unknown": 1}


@pytest.mark.skipif(sys.version_info[:2] != (3, 12), reason="the original task runtime is Python 3.12")
def test_complete_constructed_trace_exports_only_with_matching_p2_evidence(api, tmp_path):
    task = "event-summary"
    evidence = tmp_path / "p2"
    subprocess.run([sys.executable, str(ROOT / "scripts/run_original_task.py"), "run", task,
                    "--output", str(evidence / task)], check=True, capture_output=True)
    policy = json.dumps({"version": 1, "families": [
        {"family": f"original:{task}", "purpose": "train", "tasks": [task]},
    ]}).encode()
    files, report = api["build"](evidence, policy)
    assert files["sft.jsonl"] == files["preferences.jsonl"] == []
    records = {row["source_id"]: row for row in report["cohort"]}
    for submission, observed in [("reference", "verified example"), ("partial", "duplicate rejected")]:
        source = f"original:{task}:v1:{submission}"
        record = records[source]
        sample = example(source, record["outcome"], output=observed)
        sample["messages"][0]["content"] = (ROOT / "tasks/original" / task / "instruction.md").read_text()
        envelope = {key: record[key] for key in ("source_id", "origin", "candidate_sha256", "verifier_version",
                                                 "checks_sha256", "artifact_sha256")}
        envelope.update(schema_version=1, complete=True, messages=sample["messages"], tools=sample["tools"])
        (evidence / task / submission / "trajectory.json").write_text(json.dumps(envelope))

    files, report = api["build"](evidence, policy)
    assert len(files["sft.jsonl"]) == len(files["preferences.jsonl"]) == 1
    assert [s["source_id"] for s in files["provenance.jsonl"][1]["sources"]] == [
        "original:event-summary:v1:reference", "original:event-summary:v1:partial",
    ]
    assert report["trajectory_counts"]["complete"] == 2

    hidden = evidence / task / "reference/verification/duplicate-delivery/result.json"
    original = hidden.read_bytes()
    hidden.write_bytes(b"{}\n")
    files, report = api["build"](evidence, policy)
    assert files["sft.jsonl"] == files["preferences.jsonl"] == []
    invalid = next(row for row in report["cohort"] if row["source_id"].endswith(":reference"))
    assert invalid["reason"] == "invalid_verification_evidence"

    matrix_file = evidence / task / "matrix.json"
    matrix = json.loads(matrix_file.read_bytes())
    del matrix["matrix"]["alternative"]["source"]
    matrix_file.write_text(json.dumps(matrix))
    (evidence / task / "claim-only/final-reply.txt").write_bytes(b"\xff")
    files, report = api["build"](evidence, policy)
    assert report["screening_comparison"]["denominator"] == 5
    assert report["screening_comparison"]["final_reply_only"]["excluded_by_reason"]["invalid_final_reply"] == 1
    unknown = next(row for row in report["cohort"] if row["source_id"].endswith(":alternative"))
    assert unknown["origin"] == "unknown"
    assert unknown["trajectory_status"] == "unknown_origin"
    hidden.write_bytes(original)

    (evidence / task / "reference/verification/submitted-result.json").write_text("{}\n")
    files, report = api["build"](evidence, policy)
    assert files["sft.jsonl"] == files["preferences.jsonl"] == []
    invalid = next(row for row in report["cohort"] if row["source_id"].endswith(":reference"))
    assert invalid["reason"] == "invalid_verification_evidence"
