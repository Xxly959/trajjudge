#!/usr/bin/env python
"""Aggregate human review CSVs for Module C (P1-3 blindspots & Claw-48 adjudication).

Never fabricates human verdicts: when CSV rows are unfilled, writes
``status: "pending_human_review"`` to ``reports/p13_human_review.json``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402

VALID_BLINDSPOT_VERDICTS = frozenset({"confirmed", "false_alarm", "unclear"})
VALID_CLAW_LABELS = frozenset({"pass", "fail"})
VALID_FAVORS = frozenset({"human", "ai", "other"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summarize_reviews(
    *,
    blindspot_csv: Path = root / "annotation/round3_blindspots.csv",
    claw_csv: Path = root / "annotation/round3_claw48_adjudication.csv",
    out_path: Path | None = root / "reports/p13_human_review.json",
) -> dict[str, Any]:
    bs_rows = list(csv.DictReader(blindspot_csv.open("r", encoding="utf-8", newline=""))) if blindspot_csv.is_file() else []
    cl_rows = list(csv.DictReader(claw_csv.open("r", encoding="utf-8", newline=""))) if claw_csv.is_file() else []

    bs_counts: Counter[str] = Counter()
    bs_by_domain: dict[str, Counter[str]] = {}
    bs_completed = 0
    for r in bs_rows:
        v = str(r.get("human_verdict") or "").strip().lower()
        if not v:
            continue
        if v not in VALID_BLINDSPOT_VERDICTS:
            raise ValueError(f"invalid human_verdict {v!r}; expected one of {sorted(VALID_BLINDSPOT_VERDICTS)}")
        if not str(r.get("human_reason") or "").strip():
            raise ValueError("human_reason is required whenever human_verdict is filled")
        bs_completed += 1
        bs_counts[v] += 1
        dom = str(r.get("domain") or "unknown")
        bs_by_domain.setdefault(dom, Counter())[v] += 1

    cl_completed = 0
    cl_final: Counter[str] = Counter()
    cl_favors: Counter[str] = Counter()
    for r in cl_rows:
        fl = str(r.get("final_label") or "").strip().lower()
        fav = str(r.get("favors") or "").strip().lower()
        if not fl and not fav:
            continue
        if fl not in VALID_CLAW_LABELS:
            raise ValueError(f"invalid final_label {fl!r}; expected pass/fail")
        if not fav:
            if fl == str(r.get("human_v2_label") or "").strip().lower():
                fav = "human"
            elif fl == str(r.get("silver_label") or "").strip().lower():
                fav = "ai"
            else:
                fav = "other"
        if fav not in VALID_FAVORS:
            raise ValueError(f"invalid favors {fav!r}; expected human/ai/other")
        if not str(r.get("human_reason") or "").strip():
            raise ValueError("human_reason is required whenever final_label is filled")
        cl_completed += 1
        cl_final[fl] += 1
        cl_favors[fav] += 1

    bs_total = len(bs_rows)
    cl_total = len(cl_rows)
    bs_done = bs_total > 0 and bs_completed == bs_total
    cl_done = cl_total > 0 and cl_completed == cl_total

    overall_status = (
        "completed"
        if (bs_done and cl_done)
        else ("partial" if (bs_completed > 0 or cl_completed > 0) else "pending_human_review")
    )

    confirmed = bs_counts.get("confirmed", 0)
    precision = round(confirmed / bs_completed, 4) if bs_completed else None
    precision_all_13 = round(confirmed / bs_total, 4) if bs_done and bs_total else None

    report = {
        "generated_at": _utc_now(),
        "status": overall_status,
        "blindspots_c1": {
            "total_flagged_by_silver": bs_total,
            "reviewed_count": bs_completed,
            "completed": bs_done,
            "verdict_counts": {
                "confirmed": bs_counts.get("confirmed", 0),
                "false_alarm": bs_counts.get("false_alarm", 0),
                "unclear": bs_counts.get("unclear", 0),
            },
            "ai_blindspot_precision_reviewed": precision,
            "ai_blindspot_precision_over_13": precision_all_13,
            "by_domain": {k: dict(sorted(v.items())) for k, v in sorted(bs_by_domain.items())},
        },
        "claw48_adjudication_c2": {
            "total_disagreements": cl_total,
            "reviewed_count": cl_completed,
            "completed": cl_done,
            "final_label_counts": dict(sorted(cl_final.items())),
            "favors_counts": {
                "human": cl_favors.get("human", 0),
                "ai": cl_favors.get("ai", 0),
                "other": cl_favors.get("other", 0),
            },
        },
    }
    if out_path is not None:
        atomic_text(out_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blindspot-csv", type=Path, default=root / "annotation/round3_blindspots.csv")
    parser.add_argument("--claw-csv", type=Path, default=root / "annotation/round3_claw48_adjudication.csv")
    args = parser.parse_args(argv)
    rep = summarize_reviews(blindspot_csv=args.blindspot_csv, claw_csv=args.claw_csv)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
