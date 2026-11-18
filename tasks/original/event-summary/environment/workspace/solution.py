"""Starter that handles the visible sample but assumes delivery order."""

import json
from pathlib import Path
import sys


def main():
    source, target = map(Path, sys.argv[1:])
    runs = {}
    total = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        run_id = event["run_id"]
        count = runs.get(run_id, {}).get("unique_events", 0) + 1
        runs[run_id] = {key: event[key] for key in ("run_id", "attempt", "status")}
        runs[run_id]["unique_events"] = count
        total += 1
    result = {"runs": [runs[key] for key in sorted(runs)], "unique_events": total}
    target.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                      encoding="utf-8")


if __name__ == "__main__":
    main()
