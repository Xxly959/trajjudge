"""Evaluate the delivered JSON and run the candidate against fixed black-box cases."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def canonical(document):
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verifier_version(cases):
    return digest(canonical({
        "verify.py": digest(Path(__file__).read_bytes()),
        "cases.py": digest(cases.read_bytes()),
    }))


def artifact_check(path, expected):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return "invalid_artifact"
    if not path.exists():
        return "missing_artifact" if expected is not None else "ok"
    if expected is None:
        return "unexpected_artifact"
    return "ok" if path.read_bytes() == expected else "artifact_mismatch"


def check_case(workspace, evidence, case):
    with TemporaryDirectory(prefix="trajjudge-case-") as directory:
        work = Path(directory)
        shutil.copyfile(workspace / "solution.py", work / "solution.py")
        for name, content in case["inputs"].items():
            (work / name).write_bytes(content)
        result_path = work / "result.json"
        old = case.get("prior_output")
        if old is not None:
            result_path.write_bytes(old)
        command = ["solution.py", *case["args"], "result.json"]
        expected_exit = case.get("exit", 0)
        expected = old if expected_exit else canonical(case["expected"])
        try:
            proc = subprocess.run([sys.executable, "-I", *command], cwd=work,
                                  env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C", "TZ": "UTC"},
                                  capture_output=True, timeout=5)
        except subprocess.TimeoutExpired as exc:
            (evidence / "stdout.txt").write_bytes(exc.stdout or b"")
            (evidence / "stderr.txt").write_bytes(exc.stderr or b"")
            if result_path.is_file() and not result_path.is_symlink():
                shutil.copyfile(result_path, evidence / "result.json")
            return {"status": "candidate_timeout", "exit": None, "expected_exit": expected_exit, "command": command}
        (evidence / "stdout.txt").write_bytes(proc.stdout)
        (evidence / "stderr.txt").write_bytes(proc.stderr)
        if result_path.is_file() and not result_path.is_symlink():
            shutil.copyfile(result_path, evidence / "result.json")
        status = artifact_check(result_path, expected)
        if proc.returncode != expected_exit:
            status = "unexpected_exit"
        elif expected_exit and not proc.stderr.strip():
            status = "missing_error_message"
        return {"status": status, "exit": proc.returncode, "expected_exit": expected_exit, "command": command}


def verify(workspace, cases_path, output):
    if not workspace.is_dir():
        raise OSError("workspace directory is unavailable")
    suite = runpy.run_path(str(cases_path))
    checks = []
    delivered = workspace / "result.json"
    if delivered.is_file() and not delivered.is_symlink():
        shutil.copyfile(delivered, output / "submitted-result.json")
    checks.append({"id": "submitted-artifact", "clauses": ["delivery", "output"],
                   "status": artifact_check(delivered, canonical(suite["SUBMITTED_RESULT"]))})
    candidate = workspace / "solution.py"
    if not candidate.is_file() or candidate.is_symlink():
        checks.append({"id": "candidate-source", "clauses": ["delivery"], "status": "missing_candidate"})
        return checks
    for case in suite["CASES"]:
        evidence = output / case["id"]
        evidence.mkdir()
        checks.append({"id": case["id"], "clauses": case["clauses"], **check_case(workspace, evidence, case)})
    return checks


def main():
    # Task A accepts integers without a digit limit. The suite uses a fixed input.
    sys.set_int_max_str_digits(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True)
    except OSError as exc:
        print(f"verifier infrastructure error: {exc}", file=sys.stderr)
        return 2
    report = {"verifier_version": None, "checks": []}
    try:
        report["verifier_version"] = verifier_version(args.cases)
        report["checks"] = verify(args.workspace, args.cases, args.output)
        status = 0 if all(check["status"] == "ok" for check in report["checks"]) else 1
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
        report["infrastructure_error"] = f"{type(exc).__name__}: {exc}"
        status = 2
    report["exit"] = status
    try:
        (args.output / "checks.json").write_bytes(canonical(report))
    except OSError as exc:
        print(f"verifier infrastructure error: {exc}", file=sys.stderr)
        return 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
