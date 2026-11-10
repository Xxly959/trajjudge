"""Summarize P2 manifests: completion and official pass/fail per config (official = DeepSeek-rescored, not leaderboard)."""

import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for config in ("flash-think-off", "flash-think-on"):
    path = root / "outputs" / "claw_eval" / "p2" / config / "manifest.jsonl"
    if not path.is_file():
        continue
    latest = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        latest[row["task_id"]] = row
    c = Counter()
    for row in latest.values():
        c["complete/" + str((row.get("trial") or {}).get("passed"))] += row["status"] == "complete"
        c["stopped"] += row["status"] != "complete"
    print(config, dict(+c))
