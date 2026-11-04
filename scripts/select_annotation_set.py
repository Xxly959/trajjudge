#!/usr/bin/env python
"""Pick trajectories to annotate from completed P2 runs (stratified, failure-oversampled).

Writes outputs/p2/annotation_set.json (what the annotator's build step needs: no scores) and
outputs/p2/annotation_meta.json (private: official scores, category, config). Run once.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from trajjudge.adapter import read_jsonl  # noqa: E402
from trajjudge.artifacts import artifact_path  # noqa: E402
from trajjudge.sampling import select_for_annotation  # noqa: E402

COUNT, SEED = 50, 20261105
CONFIGS = ("flash-think-off", "flash-think-on")

if __name__ == "__main__":
    tasks = root.parent / "claw-eval" / "tasks"
    rows, items = [], {}
    for config in CONFIGS:
        manifest = root / "outputs" / "claw_eval" / "p2" / config / "manifest.jsonl"
        if not manifest.is_file():
            continue
        for line in manifest.read_text().splitlines():
            row = json.loads(line)
            if row["status"] != "complete":
                continue
            trace = artifact_path(row["trace"], root)
            events = read_jsonl(trace)
            trace_id = next(e["trace_id"] for e in events if e.get("type") == "trace_start")
            official = [e for e in events if e.get("type") == "grading_result"][-1]
            spec = yaml.safe_load((tasks / row["task_id"] / "task.yaml").read_text())
            sidecar = artifact_path(row["sidecar"], root)
            items[trace_id] = {"trace_id": trace_id, "trace": str(trace), "sidecar": str(sidecar), "criteria": spec.get("judge_rubric")}
            rows.append({"trace_id": trace_id, "task_id": row["task_id"], "category": spec.get("category", "?"), "config": config,
                         "difficulty": spec.get("difficulty"), "passed": bool(official["passed"]), "task_score": official["task_score"]})
    chosen = select_for_annotation(rows, COUNT, seed=SEED)
    out = root / "outputs" / "p2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "annotation_set.json").write_text(json.dumps([items[r["trace_id"]] for r in chosen], indent=1))
    (out / "annotation_meta.json").write_text(json.dumps({"all_candidates": rows, "chosen": chosen}, indent=1))
    print(f"{len(rows)} complete traces; {len(chosen)} chosen;",
          "official fail/pass:", dict(Counter(r["passed"] for r in chosen)),
          "configs:", dict(Counter(r["config"] for r in chosen)))
