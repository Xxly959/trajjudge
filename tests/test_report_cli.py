"""Report repeat panels from the actual manifest rather than a CLI default."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from trajjudge.cache import make_key


def test_five_repeat_manifest_is_used_and_conflicting_override_rejected(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("report_cli", Path(__file__).parents[1] / "scripts/report_experiments.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "root", tmp_path)
    source = tmp_path / "outputs/p3/p3-deepseek-flash.jsonl"
    source.parent.mkdir(parents=True)
    descriptors = [{"repeat_id": i, "trace_id": "t"} for i in range(5)]
    rows = [{"trace_id": "t", "repeat_id": i, "score": score, "variant": "original",
             "config": "accuracy|direct", "grader": "trajectory_accuracy", "judge_model": "test",
             "status": "ok", "job_id": make_key(descriptors[i])} for i, score in enumerate([1, 1, 1, 3, 3])]
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))
    meta = tmp_path / "outputs/p2/annotation_meta.json"
    meta.parent.mkdir()
    meta.write_text(json.dumps({"chosen": [{"trace_id": "t", "task_id": "task"}]}))
    manifest = tmp_path / "runs/p3-deepseek-flash/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"plan": {"jobs": descriptors}}))
    monkeypatch.setattr("sys.argv", ["report", "p3"])
    assert module.main() == 0
    result = json.loads((tmp_path / "reports/p3.json").read_text())
    assert result["evaluated_traces"] == 1
    assert result["analysis"][0]["expected_repeats"] == 5
    assert result["analysis"][0]["summary"]["flip_rate"] == 1
    monkeypatch.setattr("sys.argv", ["report", "p3", "--repeats", "3"])
    with pytest.raises(ValueError, match="conflicts with manifest"):
        module.main()


@pytest.mark.parametrize(("variants", "missing", "expected"), [
    (("original", "L2/tool"), False, "complete"),
    (("L2/tool",), False, "partial_unverified_coverage"),
    (("original", "L2/tool"), True, "partial_identity_mismatch"),
])
def test_p4_completion_requires_manifest_and_valid_pairs(tmp_path, monkeypatch, variants, missing, expected):
    spec = importlib.util.spec_from_file_location("report_cli", Path(__file__).parents[1] / "scripts/report_experiments.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "root", tmp_path)
    monkeypatch.setitem(sys.modules, "experiment",
                        SimpleNamespace(human_fail_ids=lambda *, expected_unlabeled: {"t"}))
    source = tmp_path / "outputs/p4/p4-deepseek-flash.jsonl"
    source.parent.mkdir(parents=True)
    descriptors = [{"trace_id": "t", "repeat_id": 0, "variant": variant} for variant in variants]
    rows = [{**item, "config": "accuracy|direct", "grader": "trajectory_accuracy",
             "judge_model": "test", "score": 1 if item["variant"] == "original" else 3,
             "status": "ok", "job_id": make_key(item)} for item in descriptors]
    if missing:
        rows.pop(0)
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    meta = tmp_path / "outputs/p2/annotation_meta.json"
    meta.parent.mkdir()
    meta.write_text(json.dumps({"chosen": [{"trace_id": "t", "task_id": "task"}]}))
    manifest = tmp_path / "runs/p4-deepseek-flash/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"plan": {"jobs": descriptors}}))
    monkeypatch.setattr("sys.argv", ["report", "p4", "--expected-unlabeled", "2"])
    assert module.main() == 0
    result = json.loads((tmp_path / "reports/p4.json").read_text())
    assert result["status"] == expected
    if expected == "complete":
        assert result["analysis"][0]["baseline_fail_observations"] == 1
        assert result["analysis"][0]["fail_to_pass_observations"] == 1
