"""Write configs/p2_tasks_hard.json: extra long-horizon tasks (31-50 turns) to raise the official-failure rate."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from trajjudge.sampling import load_candidates, stratified_sample

if __name__ == "__main__":
    pool = [r for r in load_candidates(root.parent / "claw-eval" / "tasks", max_turns=50) if r["max_turns"] > 30]
    chosen = stratified_sample(pool, {"hard": 14, "medium": 6}, seed=20261105)
    (root / "configs" / "p2_tasks_hard.json").write_text(json.dumps(chosen, indent=1) + "\n")
    print(len(pool), "candidates;", len(chosen), "chosen;", dict(Counter((r["category"], r["difficulty"]) for r in chosen)))
