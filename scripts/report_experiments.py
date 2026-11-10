#!/usr/bin/env python
"""Recompute stage status/metrics from local evidence only; never call a model."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.agreement import self_consistency
from trajjudge.analysis import agreement_with_clusters, injection_report, join_labels, stability_report
from trajjudge.annotation import read_labels
from trajjudge.artifacts import atomic_text
from trajjudge.cache import make_key
from trajjudge.judging import load_rows, latest_rows
from trajjudge.usage import UsageLog, load_pricing, summarize, budget_cost, load_reservations
from dataclasses import asdict


def main() -> int:
    """Write numeric reports, including explicit pending status when evidence is absent."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("p2", "p3", "p4", "probe", "controls"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--repeats", type=int, help="must match the run manifest; required for legacy inputs")
    parser.add_argument("--expected-unlabeled", type=int, default=0,
                        help="P4 only: require this exact number of unlabeled traces and exclude them")
    args = parser.parse_args()
    phase = args.phase
    if args.expected_unlabeled < 0 or (args.expected_unlabeled and phase != "p4"):
        parser.error("--expected-unlabeled requires a nonnegative count and P4")
    path = args.input or root / "outputs" / phase / f"{phase}-deepseek-flash.jsonl"
    grades = latest_rows(load_rows(path))
    manifest_path = root / "runs" / path.stem / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    repeats = args.repeats
    if phase == "p3" and grades:
        if manifest and manifest.get("plan", {}).get("jobs"):
            repeat_ids = sorted({d["repeat_id"] for d in manifest["plan"]["jobs"]})
            if repeat_ids != list(range(len(repeat_ids))) or len(repeat_ids) < 3:
                raise ValueError("manifest requires a contiguous panel of at least three repeats")
            if repeats is not None and repeats != len(repeat_ids):
                raise ValueError("repeat override conflicts with manifest")
            repeats = len(repeat_ids)
        elif repeats is None:
            raise ValueError("legacy stability input requires explicit --repeats")
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text())
    tasks = {r["trace_id"]: r["task_id"] for r in meta["chosen"]}
    result = {"phase": phase, "status": "pending", "source": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
              "score_rows": len(grades), "selected_traces": len(tasks), "resamples": 2000,
              "evaluated_traces": len({r["trace_id"] for r in grades}),
              "latest_row_usage": {"api_calls": sum(r.get("usage", {}).get("api_calls", 0) for r in grades),
                            "cached_calls": sum(r.get("usage", {}).get("cached_calls", 0) for r in grades)},
              "limitations": ["Single provider and annotator; official scores partly LLM-derived, not truth.",
                  "Failure-enriched, mixed-cap sample; not leaderboard comparable or a controlled thinking ablation.",
                  "No significance claim; missing/error rows retained in coverage; task-cluster bootstrap CIs."]}
    if phase == "p2":
        labels = read_labels(root / "annotation/labels.csv")
        key = json.loads((root / "outputs/annotation/key.json").read_text())
        joined = join_labels(meta["chosen"], key, labels, grades)
        result.update({k: v for k, v in joined.items() if k != "rows"})
        if joined["rows"]:
            result["agreement"] = agreement_with_clusters(joined["rows"])
            result["status"] = "complete" if joined["labeled"] == joined["selected"] and not any(joined["missing_scores"].values()) else "partial"
        round2_path = root / "outputs/annotation/round2_key.json"
        if round2_path.exists():
            second = json.loads(round2_path.read_text())
            first_labels = {r["blind_id"]: r["label"] == "pass" for r in labels if r["round"] == "1" and r["label"]}
            repeated = {second[r["blind_id"]]: r["label"] == "pass" for r in labels if r["round"] == "2" and r["label"]}
            result["self_consistency"] = self_consistency(first_labels, repeated)
    elif grades:
        if phase == "probe":
            groups = {}
            for r in grades:
                groups.setdefault(r["config"], []).append(r)
            result["analysis"] = [{"config": name, "observations": len(group), "errors": sum(r["status"] != "ok" for r in group),
                "distinct_reasons": len({r["reason"] for r in group if r["status"] == "ok"}),
                "scores": [r["score"] for r in group], "completion_tokens": [r["usage"].get("completion_tokens") for r in group]}
                for name, group in sorted(groups.items())]
            result["status"] = "descriptive_probe"
            result["limitations"].append("Output variety cannot prove the server honored or ignored temperature; request acceptance and distributions are distinct evidence.")
        elif phase == "p3":
            result["analysis"] = stability_report(grades, repeats=repeats, task_ids=tasks)
            result["status"] = "complete" if all(g["incomplete_traces"] == 0 for g in result["analysis"]) else "partial"
        else:
            result["analysis"] = injection_report(grades, task_ids=tasks)
            result["paired_change_counts"] = {grader: {
                "paired": sum(g["paired_observations"] for g in result["analysis"] if g["grader"] == grader),
                "changed": sum(g["changed_observations"] for g in result["analysis"] if g["grader"] == grader)}
                for grader in sorted({g["grader"] for g in result["analysis"]})}
            result["status"] = "exploratory_controls" if phase == "controls" else "partial_unverified_coverage"
            if phase == "p4":
                from experiment import human_fail_ids
                allowed = human_fail_ids(expected_unlabeled=args.expected_unlabeled)
                if any(r["trace_id"] not in allowed for r in grades):
                    raise ValueError("formal P4 evidence includes traces without an owner fail label")
                result["annotation_coverage"] = {"unlabeled": args.expected_unlabeled,
                                                 "eligible_human_fail_traces": len(allowed)}
            else:
                result["limitations"].append("Rule-control changes are lexical behavior, not evidence of LLM manipulation or defense effectiveness.")
        if manifest:
            planned = len(manifest.get("plan", {}).get("jobs", [])) or manifest.get("total_jobs", 0)
            result["planned_jobs"] = planned
            result["successful_rows"] = sum(r["status"] == "ok" for r in grades)
            if phase in ("p3", "p4") and result["successful_rows"] != planned:
                result["status"] = "partial"
            if manifest.get("plan", {}).get("jobs"):
                planned_ids = {make_key(d) for d in manifest["plan"]["jobs"]}
                actual_ids = {r.get("job_id") for r in grades}
                if actual_ids != planned_ids:
                    result["status"] = "partial_identity_mismatch"
                elif (phase == "p4" and result["successful_rows"] == planned == len(planned_ids)
                      and {r["trace_id"] for r in grades if r.get("variant") != "original"} == allowed
                      and result["analysis"]
                      and all(not group["unpaired_observations"] for group in result["analysis"])):
                    result["status"] = "complete"
        elif phase != "controls":
            result["status"] = "partial_missing_manifest"
    ledger = UsageLog(root / "outputs/usage/usage.jsonl").read()
    result["phase_usage"] = asdict(summarize([r for r in ledger if r.tag.startswith(phase + "/")], load_pricing(root / "configs/pricing_p3.yaml")))
    phase_records = [r for r in ledger if r.tag.startswith(phase + "/")]
    result["budget_accounting"] = {"conservative_cost_with_reservations_usd": budget_cost(
        phase_records, load_pricing(root / "configs/pricing_p3.yaml"), load_reservations(root / "outputs/usage/usage.jsonl")),
        "unknown_attempts": sum(not r.cached and not r.usage_known for r in phase_records),
        "basis": "budget-only bounds; unknown original token usage remains unknown"}
    atomic_text(root / "reports" / f"{phase}.json", json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"phase": phase, "status": result["status"], "score_rows": len(grades)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
