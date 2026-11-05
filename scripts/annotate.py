#!/usr/bin/env python
"""Blind annotation CLI: build the kit, label interactively, plan a re-label round, check the CSV.

    annotate.py build --set outputs/p2/annotation_set.json   # writes annotation/ + private key
    annotate.py label                                         # interactive, resumable
    annotate.py relabel --count 10                            # start round 2 on a random subset
    annotate.py check

The viewer shows the task criteria and conversation only: never judge scores,
official scores, model names or real trace ids. Labels are yours alone.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import annotation as kit  # noqa: E402
from trajjudge.adapter import adapt_trace  # noqa: E402

ANN = root / "annotation"
KEY = root / "outputs" / "annotation" / "key.json"
CSV_PATH = ANN / "labels.csv"


def build(set_path: Path) -> None:
    """Render every selected trace under a blind id and create the empty label CSV."""
    items = json.loads(set_path.read_text())
    if CSV_PATH.exists() or KEY.exists():
        sys.exit("annotation labels or private key already exist; refusing to overwrite")
    mapping = kit.blind_ids([i["trace_id"] for i in items], seed=kit.new_seed())
    (ANN / "traces").mkdir(parents=True, exist_ok=True)
    for item in items:
        for key in ("trace", "sidecar"):
            if item.get(f"{key}_sha256") and hashlib.sha256(Path(item[key]).read_bytes()).hexdigest() != item[f"{key}_sha256"]:
                sys.exit("frozen annotation evidence changed; refusing to build")
        trace = adapt_trace(Path(item["trace"]), sidecar_path=Path(item["sidecar"]) if item.get("sidecar") else None)
        text = kit.render_trace(trace.messages, prompt_criteria=item.get("criteria"), blind_id=mapping[item["trace_id"]], max_block_chars=None)
        (ANN / "traces" / f"{mapping[item['trace_id']]}.md").write_text(text, encoding="utf-8")
    kit.write_template(CSV_PATH, sorted(mapping.values()))
    KEY.parent.mkdir(parents=True, exist_ok=True)
    KEY.write_text(json.dumps(mapping, indent=1))
    print(f"{len(mapping)} traces in annotation/traces; private key at {KEY.relative_to(root)} (do not open it while labelling)")


def _save(rows: list[dict[str, str]]) -> None:
    kit.save_labels(CSV_PATH, rows)


def label(round_id: str) -> None:
    """Prompt for pass/fail and a one-line reason for each unlabeled row of ``round_id``."""
    rows = kit.read_labels(CSV_PATH)
    todo = [r for r in rows if r["round"] == round_id and not r["label"]]
    print(f"{len(todo)} unlabeled in round {round_id}. Enter p / f, or s to skip, q to quit.")
    for row in todo:
        print("\n" + "=" * 78 + "\n" + (ANN / "traces" / f"{row['blind_id']}.md").read_text(encoding="utf-8"))
        answer = ""
        while answer not in {"p", "f", "s", "q"}:
            answer = input("label [p/f/s/q]: ").strip().lower()
        if answer == "q":
            break
        if answer == "s":
            continue
        reason = ""
        while not reason.strip():
            reason = input("one-line reason: ")
        row.update(label="pass" if answer == "p" else "fail", reason=reason.strip(),
                   annotated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _save(rows)
    print("saved.")


def relabel(count: int) -> None:
    """Append blank round-2 rows for a random subset (the original labels are not shown again)."""
    rows = kit.read_labels(CSV_PATH)
    if any(r["round"] == "2" for r in rows):
        sys.exit("round 2 already exists")
    first_rows = [r for r in rows if r["round"] == "1" and r["label"]]
    if not first_rows:
        sys.exit("finish round 1 before scheduling a re-label round")
    if any(not r["label"] for r in rows if r["round"] == "1"):
        sys.exit("round 1 is incomplete; finish or explicitly exclude unresolved items first")
    last = max(datetime.fromisoformat(r["annotated_at"]) for r in first_rows)
    if datetime.now(timezone.utc) < last + timedelta(days=2):
        sys.exit("wait at least two days after round 1 before re-labeling")
    first = [r["blind_id"] for r in first_rows]
    second_key = KEY.with_name("round2_key.json")
    if second_key.exists():
        sys.exit("round 2 key already exists; inspect recovery state without overwriting labels")
    private = {}
    for blind_id in kit.relabel_sample(first, count, seed=kit.new_seed()):
        fresh = f"R{kit.new_seed():08x}"
        while fresh in private or fresh in first:
            fresh = f"R{kit.new_seed():08x}"
        private[fresh] = blind_id
        text = (ANN / "traces" / f"{blind_id}.md").read_text()
        (ANN / "traces" / f"{fresh}.md").write_text(text.replace(f"# Trace {blind_id}\n", f"# Trace {fresh}\n", 1))
        rows.append({"blind_id": fresh, "label": "", "reason": "", "annotated_at": "", "round": "2"})
    second_key.write_text(json.dumps(private, indent=2))
    _save(rows)
    print(f"added {min(count, len(first))} round-2 rows; run `label --round 2` after a few days")


def check() -> None:
    """Print validation problems and progress."""
    rows = kit.read_labels(CSV_PATH)
    expected = sorted(json.loads(KEY.read_text()).values())
    round2_key = KEY.with_name("round2_key.json")
    if round2_key.exists():
        expected += sorted(json.loads(round2_key.read_text()))
    problems = kit.validate_labels(rows, sorted(json.loads(KEY.read_text()).values()))
    known = set(expected)
    problems = [p for p in problems if not (p.startswith("unknown blind_id ") and p.split()[-1] in known)]
    done = sum(bool(r["label"]) for r in rows)
    print(f"{done}/{len(rows)} rows labeled; problems: {problems or 'none'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--set", required=True, type=Path)
    l = sub.add_parser("label")
    l.add_argument("--round", default="1")
    r = sub.add_parser("relabel")
    r.add_argument("--count", type=int, default=10)
    sub.add_parser("check")
    args = parser.parse_args()
    {"build": lambda: build(args.set), "label": lambda: label(args.round),
     "relabel": lambda: relabel(args.count), "check": check}[args.cmd]()
