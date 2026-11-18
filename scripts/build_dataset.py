#!/usr/bin/env python3
"""Build a private, offline dataset from the P2 run and first-round judgments."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trajjudge.adapter import adapt_trace, read_jsonl  # noqa: E402
from trajjudge.agreement import THRESHOLDS  # noqa: E402
from trajjudge.annotation import read_labels, validate_labels  # noqa: E402
from trajjudge.artifacts import artifact_path, atomic_text  # noqa: E402
from trajjudge.score_scales import SCALES  # noqa: E402


CONFIGS = ("flash-think-off", "flash-think-on")
SCHEMA_VERSION = 1
SNAPSHOT_VERSION = 2
SNAPSHOT_FILES = ("trajectories.jsonl", "quality.json")
INPUT_FILES = (
    "outputs/p2/annotation_meta.json", "outputs/p2/annotation_set.json",
    "outputs/annotation/key.json", "annotation/labels.csv", "outputs/p2/p2-deepseek-flash.jsonl",
    *(f"outputs/claw_eval/p2/{config}/manifest.jsonl" for config in CONFIGS),
)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    def unique_keys(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate JSON key in frozen annotation input: {path.name}")
            obj[key] = value
        return obj

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def index_traces(rows, name):
    indexed = {}
    for row in rows:
        trace_id = row["trace_id"]
        if trace_id in indexed:
            raise ValueError(f"duplicate trace ID in {name}: {trace_id}")
        indexed[trace_id] = row
    return indexed


def finite_score(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def json_score(value):
    # Invalid numerical values remain missing/invalid instead of emitting non-JSON tokens.
    return value if finite_score(value) else None


def valid_openjudge_grade(grade):
    name, score = grade["grader"], grade["score"]
    limits = SCALES.get(name) if isinstance(name, str) else None
    return (grade["status"] == "ok" and limits is not None and finite_score(score)
            and limits[0] <= score <= limits[1])


def load_judgments(root):
    p2 = root / "outputs/p2"
    meta = read_json(p2 / "annotation_meta.json")
    candidates = index_traces(meta["all_candidates"], "annotation candidates")
    chosen = index_traces(meta["chosen"], "frozen choices")
    frozen = index_traces(read_json(p2 / "annotation_set.json"), "frozen evidence")
    key = read_json(root / "outputs/annotation/key.json")
    if set(key) != set(chosen) or set(frozen) != set(chosen) or len(set(key.values())) != len(key):
        raise ValueError("blind key and frozen selection disagree")
    first_round = [row for row in read_labels(root / "annotation/labels.csv") if row["round"] == "1"]
    if validate_labels(first_round, list(key.values())):
        raise ValueError("invalid first-round annotation file; run the annotation check")
    by_blind = {row["blind_id"]: row["label"] for row in first_round}
    human = {trace_id: by_blind[blind_id] for trace_id, blind_id in key.items()}

    grades = defaultdict(list)
    seen_jobs = set()
    for grade in read_jsonl(p2 / "p2-deepseek-flash.jsonl"):
        if grade["job_id"] in seen_jobs:
            raise ValueError("duplicate OpenJudge job ID")
        seen_jobs.add(grade["job_id"])
        fields = ("job_id", "grader", "status", "score", "judge_model", "strategy", "thinking",
                  "repeat_id", "variant", "defended", "openjudge_commit")
        entry = {name: grade.get(name) for name in fields}
        entry["score"] = json_score(entry["score"])
        grades[grade["trace_id"]].append(entry)
    for rows in grades.values():
        rows.sort(key=lambda row: row["job_id"])
    return candidates, chosen, frozen, human, grades


def load_trajectory(root, run, source, sidecar, sidecar_sha256):
    trace = adapt_trace(source, sidecar_path=sidecar)
    meta = trace.metadata
    if trace.task_id != run["task_id"]:
        raise ValueError("task_id_mismatch")
    if not meta["has_trace_end"]:
        raise ValueError("missing_trace_end")
    if meta["unmapped_content"] or not trace.messages:
        raise ValueError("incomplete_message_mapping")
    official = meta["official_result"]
    provenance = {
        "trace": str(source.relative_to(root)), "trace_sha256": meta["source_sha256"],
        "sidecar": str(sidecar.relative_to(root)), "sidecar_sha256": sidecar_sha256,
        "claw_eval_commit": run.get("claw_eval_commit"), "adapter_version": meta["adapter_version"],
        "system_source": meta["system_source"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace.trace_id, "task_id": trace.task_id, "messages": trace.messages,
        "agent": {"config": run["config"], "config_sha256": run.get("config_sha256"),
                  "model": next(e.get("model") for e in meta["events"].values() if e["type"] == "trace_start")},
        "provenance": provenance,
        "judgments": {"claw_eval": {"passed": official.get("passed"), "task_score": json_score(official.get("task_score"))}
                      if official else None},
    }


def group_counts(rows, excluded):
    verdicts = Counter({"pass": 0, "fail": 0, "missing": 0})
    duplicates = Counter()
    without_judge = missing_claw = invalid_claw = judge_rows = invalid_judge = 0
    for row in rows:
        duplicates[row["task_id"], digest(json_text(row["messages"]).encode())] += 1
        judgments = row["judgments"]
        human, claw, grades = (judgments[key] for key in ("human", "claw_eval", "openjudge"))
        verdicts["missing" if human is None else "pass" if human["passed"] else "fail"] += 1
        missing_claw += claw is None or claw["passed"] is None
        invalid_claw += (claw is not None and claw["passed"] is not None
                         and (type(claw["passed"]) is not bool or not finite_score(claw["task_score"])))
        without_judge += not grades
        judge_rows += len(grades)
        invalid_judge += sum(not valid_openjudge_grade(grade) for grade in grades)
    return {
        "tasks": len({row["task_id"] for row in rows}), "trajectories": len(rows),
        "human_verdicts": dict(verdicts),
        "missing_claw_eval_verdicts": missing_claw, "invalid_claw_eval_verdicts": invalid_claw,
        "openjudge_rows": judge_rows, "invalid_openjudge_rows": invalid_judge,
        "without_openjudge_rows": without_judge,
        "exact_message_duplicate_rows": sum(count - 1 for count in duplicates.values()),
        "excluded_by_reason": dict(Counter(row["reason"] for row in excluded)),
    }


def quality_report(rows, excluded, manifest_rows, latest_runs, chosen, grades):
    human_coverage = dict.fromkeys(("labeled", "selected_unlabeled", "not_selected"), 0)
    disagreements = 0
    judge_comparisons = defaultdict(Counter)
    split_by_task = {row["task_id"]: row["split"] for row in rows}
    for exclusion in excluded:
        exclusion["split"] = split_by_task.get(exclusion["task_id"])
    split_counts = {
        split: group_counts([row for row in rows if row["split"] == split],
                            [row for row in excluded if row["split"] == split])
        for split in ("dev", "eval")
    }
    config_counts = {
        config: group_counts([row for row in rows if row["agent"]["config"] == config],
                             [row for row in excluded if row["config"] == config])
        for config in CONFIGS
    }
    for row in rows:
        judgments = row["judgments"]
        human = judgments["human"]
        if human is None:
            human_coverage["selected_unlabeled" if row["trace_id"] in chosen else "not_selected"] += 1
            continue
        human_coverage["labeled"] += 1
        official = judgments["claw_eval"]
        if official and isinstance(official["passed"], bool):
            disagreements += human["passed"] != official["passed"]
        for grade in judgments["openjudge"]:
            if not valid_openjudge_grade(grade):
                continue
            threshold = THRESHOLDS.get(grade["grader"])
            if threshold is not None:
                comparison = judge_comparisons[grade["grader"]]
                comparison["compared"] += 1
                comparison["disagreed"] += human["passed"] != (grade["score"] >= threshold)
    ids = {row["trace_id"] for row in rows}
    tool_calls = sum(len(message.get("tool_calls", [])) for row in rows for message in row["messages"])
    return {
        "schema_version": SCHEMA_VERSION, "scope": "Claw-Eval P2 sandbox trajectories; retrospective task split",
        "manifest_rows": manifest_rows, "latest_runs": latest_runs,
        "superseded_manifest_rows": manifest_rows - latest_runs,
        **group_counts(rows, excluded),
        "by_split": split_counts, "by_config": config_counts, "excluded": excluded,
        "excluded_without_split": dict(Counter(row["reason"] for row in excluded if row["split"] is None)),
        "validated_tool_calls": tool_calls,
        "human_coverage": human_coverage,
        "human_claw_disagreements": disagreements,
        "human_openjudge_comparisons": {grader: dict(counts) for grader, counts in judge_comparisons.items()},
        "selected_traces_missing_from_export": len(chosen.keys() - ids),
        "unjoined_openjudge_rows": sum(len(grades[tid]) for tid in grades.keys() - ids),
    }


def build(root):
    fingerprints = {path: digest((root / path).read_bytes()) for path in INPUT_FILES}
    candidates, chosen, frozen, human, grades = load_judgments(root)
    frozen_slots = defaultdict(list)
    for trace_id, choice in chosen.items():
        config = choice.get("config", candidates.get(trace_id, {}).get("config"))
        if config is not None:
            frozen_slots[config, choice["task_id"]].append(trace_id)
    rows, excluded, seen = [], [], set()
    manifest_rows = latest_runs = 0
    for config in CONFIGS:
        manifest = read_jsonl(root / "outputs/claw_eval/p2" / config / "manifest.jsonl")
        if any(run["config"] != config for run in manifest):
            raise ValueError(f"manifest config mismatch in {config}")
        latest = {run["task_id"]: run for run in manifest}
        manifest_rows += len(manifest)
        latest_runs += len(latest)
        for task_id, run in sorted(latest.items()):
            expected = frozen_slots[config, task_id]
            if run["status"] != "complete":
                if expected:
                    raise ValueError(f"frozen run is not complete in {config}: {task_id} ({', '.join(expected)})")
                excluded.append({"task_id": task_id, "config": config, "reason": "run_not_complete",
                                 "status": run["status"]})
                continue
            phase = "trace"
            try:
                source = artifact_path(run["trace"], root)
                source_hash = digest(source.read_bytes())
                fingerprints[str(source.relative_to(root))] = source_hash
                phase = "sidecar"
                sidecar = artifact_path(run["sidecar"], root)
                sidecar_hash = digest(sidecar.read_bytes())
                fingerprints[str(sidecar.relative_to(root))] = sidecar_hash
                phase = "trace or sidecar"
                row = load_trajectory(root, run, source, sidecar, sidecar_hash)
            except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
                if expected:
                    raise ValueError(f"invalid frozen {phase} in {config} for {task_id} ({', '.join(expected)}): "
                                     f"{type(exc).__name__}: {exc}") from None
                known = {"task_id_mismatch", "missing_trace_end", "incomplete_message_mapping"}
                reason = str(exc) if str(exc) in known else "invalid_trace_or_sidecar"
                excluded.append({"task_id": task_id, "config": config, "reason": reason})
                continue
            if row["provenance"]["trace_sha256"] != source_hash:
                raise ValueError(f"trace changed while building: {task_id} ({config})")
            trace_id = row["trace_id"]
            if trace_id in seen:
                kind = "frozen trajectory" if trace_id in frozen else "trajectory"
                raise ValueError(f"duplicate {kind} identity in latest completed runs: {trace_id}")
            seen.add(trace_id)
            candidate = candidates.get(trace_id, {})
            if candidate and (candidate["task_id"] != task_id or candidate.get("config", config) != config):
                raise ValueError(f"annotation metadata does not match manifest for {task_id}")
            if trace_id in chosen:
                choice = chosen[trace_id]
                if choice["task_id"] != task_id or choice.get("config", config) != config:
                    raise ValueError(f"frozen annotation task or config does not match manifest: {trace_id}")
            if trace_id in frozen and any(row["provenance"][field] != frozen[trace_id][field]
                                          for field in ("trace_sha256", "sidecar_sha256")):
                raise ValueError(f"frozen annotation evidence changed for {task_id}")
            row["task"] = {name: candidate.get(name) for name in ("category", "difficulty")}
            row["agent"]["max_tokens_observed"] = candidate.get("agent_caps")
            label = human.get(trace_id)
            row["judgments"]["human"] = {"passed": label == "pass", "round": 1} if label else None
            row["judgments"]["openjudge"] = grades.get(trace_id, [])
            rows.append(row)
    missing = frozen.keys() - seen
    if missing:
        raise ValueError(f"{len(missing)} frozen trace ID(s) absent from usable latest manifest runs: "
                         f"{', '.join(sorted(missing))}")
    if not rows:
        raise ValueError("no usable trajectories")
    tasks = sorted({row["task_id"] for row in rows}, key=lambda task: digest(f"dataset-v1:{task}".encode()))
    eval_tasks = set(tasks[:max(1, len(tasks) // 5)]) if len(tasks) > 1 else set()
    for row in rows:
        row["split"] = "eval" if row["task_id"] in eval_tasks else "dev"
    rows.sort(key=lambda row: (row["task_id"], row["agent"]["config"], row["trace_id"]))
    report = quality_report(rows, excluded, manifest_rows, latest_runs, chosen, grades)
    for path, sha256 in fingerprints.items():
        if digest((root / path).read_bytes()) != sha256:
            raise ValueError(f"input changed while building: {path}")
    report["input_files"] = fingerprints
    report["input_sha256"] = digest(json_text(fingerprints).encode())
    report["snapshot_version"] = SNAPSHOT_VERSION
    return rows, report


def verify_snapshot(directory, snapshot_id):
    descriptor_path = directory / "snapshot.json"
    descriptor_bytes = descriptor_path.read_bytes()
    if digest(descriptor_bytes) != snapshot_id:
        raise ValueError("snapshot.json hash does not match snapshot ID")
    descriptor = json.loads(descriptor_bytes)
    hashes = descriptor["files"]
    if descriptor["snapshot_version"] != SNAPSHOT_VERSION or set(hashes) != set(SNAPSHOT_FILES):
        raise ValueError("unsupported or incomplete snapshot descriptor")
    for name in SNAPSHOT_FILES:
        if digest((directory / name).read_bytes()) != hashes[name]:
            raise ValueError(f"{name} hash does not match snapshot.json")
    return descriptor


def check_current(target):
    snapshot_id = (target / "CURRENT").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
        raise ValueError("invalid snapshot ID in CURRENT")
    directory = target / "snapshots" / snapshot_id
    if directory.resolve() != directory:
        raise ValueError("snapshot directory must remain inside local outputs")
    verify_snapshot(directory, snapshot_id)
    return directory


def publish_snapshot(target, rows, report):
    trajectories = "".join(json_text(row) + "\n" for row in rows)
    report["trajectories_sha256"] = digest(trajectories.encode())
    quality = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    descriptor = json_text({
        "snapshot_version": SNAPSHOT_VERSION,
        "input_sha256": report["input_sha256"],
        "files": {"trajectories.jsonl": report["trajectories_sha256"], "quality.json": digest(quality.encode())},
    }) + "\n"
    snapshot_id = digest(descriptor.encode())
    snapshots = target / "snapshots"
    if snapshots.resolve() != snapshots:
        raise ValueError("snapshot store must remain inside local outputs")
    snapshots.mkdir(exist_ok=True)
    directory = snapshots / snapshot_id
    if directory.resolve() != directory:
        raise ValueError("snapshot directory must remain inside local outputs")
    if directory.exists():
        verify_snapshot(directory, snapshot_id)
    else:
        with TemporaryDirectory(prefix=".stage-", dir=snapshots) as staging:
            stage = Path(staging)
            atomic_text(stage / "trajectories.jsonl", trajectories)
            atomic_text(stage / "quality.json", quality)
            atomic_text(stage / "snapshot.json", descriptor)
            verify_snapshot(stage, snapshot_id)
            os.replace(stage, directory)
    # Readers resolve CURRENT once, then use that generation for every file.
    atomic_text(target / "CURRENT", snapshot_id + "\n")
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="P2 evidence checkout")
    parser.add_argument("--check", action="store_true", help="verify the published snapshot without reading inputs")
    args = parser.parse_args()
    root = args.root.resolve()
    target = root / "outputs/dataset"
    if target.resolve() != target:
        parser.error("dataset output must remain inside the checkout's local outputs directory")
    try:
        if args.check:
            directory = check_current(target)
            print(f"Verified {directory.relative_to(root)}")
            return
        target.mkdir(parents=True, exist_ok=True)
        with (target / ".build.lock").open("a", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows, report = build(root)
            directory = publish_snapshot(target, rows, report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        action = "check" if args.check else "build"
        parser.exit(1, f"dataset {action} failed: {exc}\n")
    print(f"{len(rows)} trajectories / {report['tasks']} tasks; {len(report['excluded'])} excluded runs")
    print(f"Published {directory.relative_to(root)}")


if __name__ == "__main__":
    main()
