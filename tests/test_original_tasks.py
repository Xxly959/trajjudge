import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_original_task.py"


@pytest.mark.skipif(sys.version_info[:2] != (3, 12), reason="the original task runtime is Python 3.12")
@pytest.mark.parametrize(("task", "partial_check"), [
    ("event-summary", "duplicate-delivery"),
    pytest.param(
        "score-join",
        "missing-result",
        marks=pytest.mark.skipif(
            not (Path(__file__).resolve().parents[1] / "tasks/original/score-join/cases.py").exists(),
            reason="eval-family private holdout suite stays local and gitignored",
        ),
    ),
])
def test_original_task_matrix_verifies_products_and_behavior(tmp_path, task, partial_check):
    out = tmp_path / "matrix"
    result = subprocess.run([sys.executable, str(RUNNER), "run", task, "--output", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / "matrix.json").read_bytes())
    matrix = report["matrix"]
    assert report["matrix_passed"] is True
    assert {name: row["verifier_exit"] for name, row in matrix.items()} == {
        "starter": 1, "reference": 0, "alternative": 0, "partial": 1, "claim-only": 1,
    }
    assert set(matrix["partial"]["failed_checks"]) == {partial_check}
    assert matrix["claim-only"]["failed_checks"] == {"submitted-artifact": "missing_artifact"}
    assert all(row["starting_files"] == matrix["starter"]["starting_files"] for row in matrix.values())
    assert matrix["reference"]["candidate_sha256"] != matrix["alternative"]["candidate_sha256"]
    reference = out / "reference/verification/submitted-result.json"
    assert reference.read_bytes() == (out / "alternative/verification/submitted-result.json").read_bytes()
    assert not (out / "claim-only/verification/submitted-result.json").exists()


def test_verifier_fault_reports_infrastructure_exit(tmp_path):
    verifier = ROOT / "tasks/original/verify.py"
    cases = tmp_path / "broken.py"
    cases.write_text("unparseable test suite !\n")
    out = tmp_path / "evidence"
    result = subprocess.run([sys.executable, str(verifier), "--workspace", str(tmp_path),
                             "--cases", str(cases), "--output", str(out)], capture_output=True, text=True)
    assert result.returncode == 2
    report = json.loads((out / "checks.json").read_bytes())
    assert report["exit"] == 2 and report["checks"] == []
    assert report["infrastructure_error"].startswith("SyntaxError:")


def test_missing_candidate_code_is_a_failed_submission(tmp_path):
    verifier = ROOT / "tasks/original/verify.py"
    cases = ROOT / "tasks/original/event-summary/cases.py"
    out = tmp_path / "evidence"
    result = subprocess.run([sys.executable, str(verifier), "--workspace", str(tmp_path),
                             "--cases", str(cases), "--output", str(out)], capture_output=True, text=True)
    assert result.returncode == 1
    report = json.loads((out / "checks.json").read_bytes())
    assert report["checks"][0]["status"] == "missing_artifact"
    assert report["checks"][1]["status"] == "missing_candidate"


def test_existing_evidence_directory_is_not_a_candidate_failure(tmp_path):
    verifier = ROOT / "tasks/original/verify.py"
    cases = ROOT / "tasks/original/event-summary/cases.py"
    out = tmp_path / "evidence"
    out.mkdir()
    previous = out / "checks.json"
    previous.write_bytes(b"previous report\n")
    result = subprocess.run([sys.executable, str(verifier), "--workspace", str(tmp_path),
                             "--cases", str(cases), "--output", str(out)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "infrastructure error" in result.stderr
    assert previous.read_bytes() == b"previous report\n"


def test_harbor_package_stages_same_verifier_without_answers_in_environment(tmp_path):
    out = tmp_path / "task"
    result = subprocess.run([sys.executable, str(RUNNER), "package", "event-summary", "--output", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    config = tomllib.loads((out / "task.toml").read_text())
    assert config["verifier"]["environment_mode"] == "shared"
    assert (out / "tests/verify.py").read_bytes() == (ROOT / "tasks/original/verify.py").read_bytes()
    assert {p.name for p in (out / "environment/workspace").iterdir()} == {"solution.py", "input.jsonl"}
    for script in (out / "solution/solve.sh", out / "tests/test.sh"):
        subprocess.run(["/bin/sh", "-n", str(script)], check=True)
