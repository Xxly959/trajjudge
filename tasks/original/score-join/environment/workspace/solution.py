"""Starter that expects one report for each run and matches only on run ID."""

import json
from pathlib import Path
import sys


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    runs_path, reports_path, target = map(Path, sys.argv[1:])
    reports = {row["run_id"]: row["status"] for row in rows(reports_path)}
    results = [
        {"task_id": run["task_id"], "run_id": run["run_id"], "scorer_version": version,
         "status": reports.get(run["run_id"], "fail")}
        for run in rows(runs_path) for version in run["scorer_versions"]
    ]
    results.sort(key=lambda row: (row["task_id"], row["run_id"], row["scorer_version"]))
    output = {"results": results, "ignored_reports": 0}
    target.write_bytes((json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())


if __name__ == "__main__":
    main()
