#!/usr/bin/env python
"""Recompute shared-draw aggregation, missingness and sensitivity from local evidence only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.agreement import THRESHOLDS
from trajjudge.analysis import join_labels
from trajjudge.annotation import read_labels
from trajjudge.artifacts import atomic_text
from trajjudge.judging import latest_rows, load_rows
from trajjudge.robustness import (aggregation_diagnostics, injection_sensitivity, missingness_report,
                                  missingness_sensitivity)


def cache_entries(cache_dir: Path) -> list[dict]:
    """Read cached completions; the tag is provenance, never the identity."""
    out = []
    for path in sorted(cache_dir.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategies", type=Path, default=root / "outputs/p3/p3-flash-strategies-4.jsonl")
    parser.add_argument("--injection", type=Path, default=root / "outputs/p4/p4-flash-human-fail-16.jsonl")
    parser.add_argument("--cache", type=Path, default=root / ".cache/llm")
    parser.add_argument("--output", type=Path, default=root / "reports/robustness_v2.json")
    args = parser.parse_args()

    strategies = latest_rows(load_rows(args.strategies))
    injection = latest_rows(load_rows(args.injection))
    entries = cache_entries(args.cache)
    result = {
        "sources": {"strategies": str(args.strategies.relative_to(root)),
                    "injection": str(args.injection.relative_to(root)),
                    "cache_entries_scanned": len(entries)},
        "aggregation": aggregation_diagnostics(strategies, entries),
        "missingness": {"p4_injection": missingness_report(injection),
                        "p3_strategies": missingness_report(strategies)},
    }

    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text())
    labels = read_labels(root / "annotation/labels.csv")
    key = json.loads((root / "outputs/annotation/key.json").read_text())
    joined = join_labels(meta["chosen"], key, labels, latest_rows(load_rows(root / "outputs/p2/p2-deepseek-flash.jsonl")))
    result["sensitivity"] = {
        grader: missingness_sensitivity(joined["rows"], grader, THRESHOLDS[grader])
        for grader in sorted(THRESHOLDS)}
    result["injection_sensitivity"] = {
        f"{grader}|defended={defended}": injection_sensitivity(
            [r for r in injection if bool(r.get("defended", False)) is defended], grader, THRESHOLDS[grader])
        for grader in sorted(THRESHOLDS) for defended in (False, True)}
    result["labeled_rows"] = joined["labeled"]
    result["missing_scores"] = joined["missing_scores"]
    atomic_text(args.output, json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    agg = result["aggregation"]
    print(json.dumps({"verified_panels": agg["draw_level"]["panels"],
                      "coverage": agg["recovery"]["coverage"],
                      "all_draws_distinct": agg["draw_level"]["all_draws_distinct"],
                      "voting_eq_min": agg["draw_level"]["voting_eq_min"],
                      "voting_lt_average_rows": agg["row_level"]["voting_lt_average"],
                      "p4_invalid": result["missingness"]["p4_injection"]["invalid"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())