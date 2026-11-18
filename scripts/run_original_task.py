#!/usr/bin/env python3
"""Run the locally authored task matrix or stage its Harbor layout."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1] / "tasks/original"
TASKS = ("event-summary", "score-join")
CLAIM = "已完成修改并生成 result.json。\n"
CONFIG = '''schema_version = "1.4"

[task]
name = "trajjudge/{task}"

[metadata]
category = "programming"
task_version = "1"

[verifier]
environment_mode = "shared"
timeout_sec = 90.0

[agent]
timeout_sec = 90.0

[environment]
network_mode = "no-network"
workdir = "/workspace"
cpus = 1
memory_mb = 1024
storage_mb = 4096
'''
DOCKERFILE = """FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
WORKDIR /workspace
COPY workspace/ /workspace/
"""
HARBOR_TEST = """#!/bin/sh
set -eu
mkdir -p /logs/verifier
status=0
python3 /tests/verify.py --workspace /workspace --cases /tests/cases.py --output /logs/verifier/evidence || status=$?
case "$status" in
  0) printf '1\n' > /logs/verifier/reward.txt ;;
  1) printf '0\n' > /logs/verifier/reward.txt ;;
  *) exit "$status" ;;
esac
"""
IMPLEMENTATION_SOURCES = {
    "starter": ["environment/workspace/solution.py"],
    "reference": ["solution/reference.py"],
    "alternative": ["submissions/alternative.py"],
    "partial": ["solution/reference.py", "submissions/partial.json"],
    "claim-only": ["solution/reference.py"],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def input_files(directory):
    return {p.relative_to(directory).as_posix(): sha(p.read_bytes()) for p in sorted(directory.rglob("*")) if p.is_file()}


def submission_cases(task):
    reference = (task / "solution/reference.py").read_text(encoding="utf-8")
    delta = json.loads((task / "submissions/partial.json").read_bytes())
    if reference.count(delta["before"]) != 1:
        raise ValueError("partial replacement must match exactly one reference fragment")
    return {
        "starter": (None, 1),
        "reference": (reference, 0),
        "alternative": ((task / "submissions/alternative.py").read_text(encoding="utf-8"), 0),
        "partial": (reference.replace(delta["before"], delta["after"]), 1),
        "claim-only": (reference, 1),
    }, delta["failed_check"]


def verify_matrix(task, output):
    starter = task / "environment/workspace"
    suite = runpy.run_path(str(task / "cases.py"))
    args = suite["SUBMISSION_ARGS"]
    submissions, partial_check = submission_cases(task)
    output.mkdir(parents=True)
    matrix = {}
    for name, (replacement, expected) in submissions.items():
        with TemporaryDirectory(prefix="trajjudge-trial-") as directory:
            workspace = Path(directory) / "workspace"
            shutil.copytree(starter, workspace)
            start = input_files(workspace)
            if start != input_files(starter) or (workspace / "result.json").exists():
                raise ValueError("candidate workspace differs from the declared clean start")
            evidence = output / name
            evidence.mkdir()
            candidate = workspace / "solution.py"
            if replacement is not None:
                candidate.write_text(replacement, encoding="utf-8")
            shutil.copyfile(candidate, evidence / "submitted-solution.py")
            delivery = None
            if name == "claim-only":
                (evidence / "final-reply.txt").write_text(CLAIM, encoding="utf-8")
            else:
                delivery = subprocess.run([sys.executable, "-I", "solution.py", *args, "result.json"],
                                          cwd=workspace, capture_output=True, timeout=10,
                                          env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C", "TZ": "UTC"})
                (evidence / "delivery-stdout.txt").write_bytes(delivery.stdout)
                (evidence / "delivery-stderr.txt").write_bytes(delivery.stderr)
            checked = subprocess.run(
                [sys.executable, str(ROOT / "verify.py"), "--workspace", str(workspace), "--cases", str(task / "cases.py"),
                 "--output", str(evidence / "verification")], capture_output=True, timeout=90,
            )
            report_path = evidence / "verification/checks.json"
            if not report_path.exists():
                raise RuntimeError(f"verifier exited {checked.returncode} without a report: {checked.stderr.decode(errors='replace')}")
            report = json.loads(report_path.read_bytes())
            failed = {check["id"]: check["status"] for check in report["checks"] if check["status"] != "ok"}
            matrix[name] = {
                "source": "constructed_fixture", "candidate_sha256": sha(candidate.read_bytes()),
                "implementation_sources": IMPLEMENTATION_SOURCES[name],
                "starting_files": start, "delivery_command": ["solution.py", *args, "result.json"] if delivery else None,
                "delivery_exit": delivery.returncode if delivery else None, "verifier_version": report["verifier_version"],
                "verifier_exit": checked.returncode, "expected_verifier_exit": expected, "checks": len(report["checks"]),
                "failed_checks": failed,
            }
            if "infrastructure_error" in report:
                matrix[name]["infrastructure_error"] = report["infrastructure_error"]
    passed = (
        all(row["verifier_exit"] == row["expected_verifier_exit"] for row in matrix.values())
        and all(row["delivery_exit"] == 0 for name, row in matrix.items() if name != "claim-only")
        and set(matrix["partial"]["failed_checks"]) == {partial_check}
        and matrix["claim-only"]["failed_checks"] == {"submitted-artifact": "missing_artifact"}
    )
    write_json(output / "matrix.json", {
        "task": task.name, "task_version": 1, "instruction_sha256": sha((task / "instruction.md").read_bytes()),
        "environment": {"python": sys.version.split()[0], "platform": sys.platform,
                        "candidate_dependencies": "standard library"},
        "matrix": matrix, "matrix_passed": passed,
    })
    print(f"{task.name}: {len(matrix)} submissions; matrix {'passed' if passed else 'failed'}")
    return 0 if passed else 1


def package(task, output):
    output.mkdir(parents=True)
    shutil.copyfile(task / "instruction.md", output / "instruction.md")
    (output / "task.toml").write_text(CONFIG.format(task=task.name), encoding="utf-8")
    shutil.copytree(task / "environment", output / "environment")
    (output / "environment/Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    solution, tests = output / "solution", output / "tests"
    solution.mkdir()
    tests.mkdir()
    shutil.copyfile(task / "solution/reference.py", solution / "reference.py")
    args = runpy.run_path(str(task / "cases.py"))["SUBMISSION_ARGS"]
    (solution / "solve.sh").write_text(
        "#!/bin/sh\nset -eu\ncd /workspace\ncp /solution/reference.py solution.py\n"
        + f"python3 solution.py {shlex.join(args)} result.json\n", encoding="utf-8",
    )
    shutil.copyfile(ROOT / "verify.py", tests / "verify.py")
    shutil.copyfile(task / "cases.py", tests / "cases.py")
    (tests / "test.sh").write_text(HARBOR_TEST, encoding="utf-8")
    for script in (solution / "solve.sh", tests / "test.sh"):
        script.chmod(0o755)
    print(f"Staged Harbor layout in {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "package"))
    parser.add_argument("task", choices=TASKS)
    parser.add_argument("--output", type=Path, required=True, help="new directory for evidence or a Harbor task")
    args = parser.parse_args()
    task = ROOT / args.task
    if args.action == "run" and sys.version_info[:2] != (3, 12):
        parser.error("the task matrix requires Python 3.12")
    try:
        if args.action == "package":
            package(task, args.output)
            return 0
        return verify_matrix(task, args.output)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"task infrastructure error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
