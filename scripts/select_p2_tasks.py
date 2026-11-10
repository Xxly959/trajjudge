"""Write configs/p2_tasks.json: deterministic stratified task selection for P2."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from trajjudge.sampling import load_candidates, stratified_sample

SEED = 20261104
QUOTAS = {"hard": 14, "medium": 16, "easy": 10}

if __name__ == "__main__":
    pool = load_candidates(root.parent / "claw-eval" / "tasks", max_turns=30)
    chosen = stratified_sample(pool, QUOTAS, seed=SEED)
    (root / "configs" / "p2_tasks.json").write_text(json.dumps(chosen, indent=1) + "\n")
    print(len(pool), "candidates;", len(chosen), "chosen;", dict(Counter(r["category"] for r in chosen)))
