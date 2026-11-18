#!/usr/bin/env python3
"""Join a pinned mini-SWE-agent evidence bundle and an optional TrajJudge P0 snapshot offline."""

import argparse
from collections import Counter, defaultdict
import fcntl
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zlib

from build_dataset import check_current, digest, json_text, publish_snapshot, SNAPSHOT_VERSION


SCHEMA_VERSION = 1
ROLES = {"system", "user", "assistant", "tool", "exit"}
MESSAGE_FIELDS = {"role", "content", "tool_calls", "tool_call_id"}
REPORT_FLAGS = {"patch_is_None", "patch_exists", "patch_successfully_applied", "resolved", "infra_failure"}


class Excluded(ValueError):
    def __init__(self, reason, detail):
        self.reason = reason
        super().__init__(detail)


def json_document(data):
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate JSON object key")
            obj[key] = value
        return obj

    def reject_constant(value):
        raise ValueError(f"invalid JSON constant {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds the supported float range")
        return number

    return json.loads(data, object_pairs_hook=unique_pairs, parse_constant=reject_constant, parse_float=finite_float)


def blob_id(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def evidence_paths(instance):
    return {
        "trajectory": f"trajs/{instance}.traj.json",
        "report": f"logs/{instance}/report.json",
        "patch": f"logs/{instance}/patch.diff",
        "test_log": f"logs/{instance}/test_output.txt.gz",
    }


def read_evidence(root, manifest, instance):
    data, refs = {}, {}
    for role, relative in evidence_paths(instance).items():
        path = root / relative
        if not path.resolve().is_relative_to(root):
            raise Excluded("invalid_evidence_path", relative)
        if relative not in manifest["git_blobs"]:
            raise Excluded("missing_evidence_reference", relative)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            raise Excluded("missing_evidence", relative) from None
        except OSError:
            raise Excluded("unreadable_evidence", relative) from None
        sha = blob_id(payload)
        if sha != manifest["git_blobs"][relative]:
            raise Excluded("git_blob_mismatch", relative)
        data[role] = payload
        refs[role] = {"path": relative, "sha256": digest(payload), "git_blob": sha,
                      "repository": manifest["repository"], "revision": manifest["revision"]}
    return data, refs


def swe_record(root, manifest, sample, unknown_fields):
    instance = sample["instance_id"]
    data, refs = read_evidence(root, manifest, instance)
    try:
        trace = json_document(data["trajectory"])
        reports = json_document(data["report"])
        if trace["instance_id"] != instance or set(reports) != {instance}:
            raise Excluded("instance_mismatch", "trajectory or report identifies another instance")
        info, report = trace["info"], reports[instance]
        if trace["trajectory_format"] != "mini-swe-agent-1.1" or info["mini_version"] != manifest["agent_version"]:
            raise Excluded("unsupported_format", "trajectory format or mini-SWE-agent version differs")
        if info["submission"].encode() != data["patch"]:
            raise Excluded("submission_mismatch", "trajectory submission differs from patch.diff")
        if any(type(report[key]) is not bool for key in REPORT_FLAGS):
            raise ValueError("report flags must be booleans")
        if report["resolved"] != sample["registered_resolved"]:
            raise Excluded("registry_result_mismatch", "report differs from registered outcome")
        if report["resolved"] and (report["infra_failure"] or not report["patch_successfully_applied"]
                                  or not report["patch_exists"] or report["patch_is_None"] or not data["patch"]):
            raise Excluded("inconsistent_report", "resolved verdict conflicts with report flags or patch")
        test_counts = {}
        for group in ("FAIL_TO_PASS", "PASS_TO_PASS", "FAIL_TO_FAIL", "PASS_TO_FAIL"):
            outcomes = report["tests_status"][group]
            if any(not isinstance(outcomes[key], list) for key in ("success", "failure")):
                raise ValueError("test status must contain success and failure lists")
            test_counts[group] = {key: len(outcomes[key]) for key in ("success", "failure")}
        if report["resolved"] and any(test_counts[g]["failure"] for g in ("FAIL_TO_PASS", "PASS_TO_PASS")):
            raise Excluded("inconsistent_report", "resolved verdict conflicts with failed required tests")
        with gzip.GzipFile(fileobj=io.BytesIO(data["test_log"])) as stream:
            log = stream.read(16 * 1024 * 1024 + 1)
        if not log or len(log) > 16 * 1024 * 1024:
            raise Excluded("invalid_test_log", "compressed test log is empty or exceeds 16 MiB unpacked")
        messages = []
        if not isinstance(trace["messages"], list) or not trace["messages"]:
            raise ValueError("messages must be a nonempty array")
        for message in trace["messages"]:
            if message["role"] not in ROLES or "content" not in message:
                raise ValueError("unsupported message role or missing content")
            messages.append({key: value for key, value in message.items() if key in MESSAGE_FIELDS})
            unknown_fields["message"].update(message.keys() - MESSAGE_FIELDS)
        unknown_fields["trajectory"].update(trace.keys() - {"instance_id", "info", "messages", "trajectory_format"})
        unknown_fields["trajectory_info"].update(info.keys() - {"mini_version", "submission", "exit_status"})
        unknown_fields["report"].update(report.keys() - REPORT_FLAGS - {"tests_status"})
    except Excluded:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OSError, EOFError, zlib.error) as exc:
        raise Excluded("invalid_evidence", type(exc).__name__) from None

    task_id = f"swe-bench:{manifest['benchmark']}:{instance}"
    status = "infra_error" if report["infra_failure"] else "pass" if report["resolved"] else "fail"
    repo = instance.rsplit("-", 1)[0].replace("__", "/", 1)
    return {
        "schema_version": SCHEMA_VERSION,
        "task": {"namespace": "swe-bench", "id": task_id, "native_id": instance, "family": task_id,
                 "benchmark": manifest["benchmark"], "repository": repo, "version": None, "task_date": None,
                 "split": "external", "isolation_group": f"swe-bench:repo:{repo}"},
        "trial": {"id": f"{task_id}:{manifest['repository']}@{manifest['revision']}", "source_type": "upstream",
                  "revision": manifest["revision"], "source_date": manifest["published_at"],
                  "harness": {"agent": "mini-SWE-agent", "agent_version": info["mini_version"],
                              "evaluator": "SWE-bench", "evaluator_version": None},
                  "transcript": {"format": trace["trajectory_format"], "messages": messages},
                  "exit_status": info.get("exit_status"), "evidence": refs},
        "outcome": {"status": status, "reverified": False, "evidence": ["report", "patch", "test_log"],
                    "test_counts": test_counts, "report_flags": {key: report[key] for key in REPORT_FLAGS}},
        "judgments": {"swe_bench": {"resolved": report["resolved"], "registry_resolved": sample["registered_resolved"]}},
    }


def claw_record(row):
    native_id = row["task_id"]
    task_id = f"claw-eval:{native_id}"
    official, provenance = row["judgments"]["claw_eval"], row["provenance"]
    passed = official.get("passed") if official else None
    return {
        "schema_version": SCHEMA_VERSION,
        "task": {"namespace": "claw-eval", "id": task_id, "native_id": native_id, "family": task_id,
                 "benchmark": "p2", "repository": None, "version": provenance["claw_eval_commit"],
                 "task_date": None, "split": row["split"], "isolation_group": task_id, **row["task"]},
        "trial": {"id": f"claw-eval:{row['trace_id']}", "source_type": "local",
                  "revision": provenance["claw_eval_commit"], "source_date": None,
                  "harness": {"agent": "Claw-Eval", "agent_version": provenance["claw_eval_commit"],
                              "evaluator": "Claw-Eval", "evaluator_version": provenance["claw_eval_commit"]},
                  "agent_config": row["agent"],
                  "transcript": {"format": "openai-messages", "messages": row["messages"]},
                  "evidence": {"trajectory": {"path": provenance["trace"], "sha256": provenance["trace_sha256"]},
                               "sidecar": {"path": provenance["sidecar"], "sha256": provenance["sidecar_sha256"]}}},
        "outcome": {"status": "pass" if passed is True else "fail" if passed is False else "unknown",
                    "reverified": False, "evidence": ["trajectory"]},
        "judgments": row["judgments"],
    }


def validate_bundle(manifest):
    for key in ("revision", "registry_revision"):
        if not re.fullmatch(r"[0-9a-f]{40}", manifest[key]):
            raise ValueError(f"{key} must be a full Git revision")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", manifest["repository"]):
        raise ValueError("invalid repository slug")
    if manifest["benchmark"] != "multilingual" or manifest["agent_version"] != "2.4.6":
        raise ValueError("unsupported benchmark or agent version")
    if not isinstance(manifest["published_at"], str) or not manifest["published_at"]:
        raise ValueError("missing source date")
    seen = set()
    for sample in manifest["instances"]:
        instance = sample["instance_id"]
        if not re.fullmatch(r"[\w.-]+__[\w.-]+-\d+", instance) or type(sample["registered_resolved"]) is not bool:
            raise ValueError("invalid sample identity or registered outcome")
        if instance in seen:
            raise ValueError(f"duplicate sample instance: {instance}")
        seen.add(instance)
    if not seen:
        raise ValueError("empty sample selection")


def source_quality(rows):
    groups = defaultdict(set)
    signatures = defaultdict(list)
    for row in rows:
        task = row["task"]
        groups[task["isolation_group"]].add(task["split"])
        signatures[digest(json_text(row["trial"]["transcript"]["messages"]).encode())].append(row["trial"]["id"])
    return {
        "tasks": len({row["task"]["id"] for row in rows}), "trials": len(rows),
        "outcomes": dict(Counter(row["outcome"]["status"] for row in rows)),
        "repositories": sorted({row["task"]["repository"] for row in rows if row["task"]["repository"]}),
        "repository_unknown": sum(row["task"]["repository"] is None for row in rows),
        "task_date_unknown": sum(row["task"]["task_date"] is None for row in rows),
        "split_groups": {key: sorted(splits) for key, splits in sorted(groups.items())},
        "groups_crossing_splits": sorted(key for key, splits in groups.items() if len(splits) > 1),
        "exact_transcript_duplicate_candidates": sorted(sorted(ids) for ids in signatures.values() if len(ids) > 1),
    }


def build(bundle, claw_root):
    bundle_data = (bundle / "bundle.json").read_bytes()
    manifest = json_document(bundle_data)
    validate_bundle(manifest)
    rows, excluded = [], []
    unknown = defaultdict(set)
    for sample in manifest["instances"]:
        try:
            rows.append(swe_record(bundle, manifest, sample, unknown))
        except Excluded as exc:
            excluded.append({"instance_id": sample["instance_id"], "reason": exc.reason, "detail": str(exc)})
    sources = {"swe-bench": {
        **source_quality(rows), "requested": len(manifest["instances"]), "excluded": excluded,
        "unknown_fields": {key: sorted(fields) for key, fields in unknown.items()},
        "repository": manifest["repository"], "revision": manifest["revision"],
        "registry_revision": manifest["registry_revision"], "archive_inventory": manifest.get("inventory"),
    }}
    inputs = {"bundle_sha256": digest(bundle_data),
              "imported_evidence": {row["task"]["id"]: {role: ref["sha256"] for role, ref in
                                                       row["trial"]["evidence"].items()} for row in rows}}
    if claw_root:
        directory = check_current(claw_root / "outputs/dataset")
        claw = [claw_record(json.loads(line)) for line in (directory / "trajectories.jsonl").read_bytes().splitlines()]
        quality = json_document((directory / "quality.json").read_bytes())
        sources["claw-eval"] = {**source_quality(claw), "excluded": quality["excluded"],
                               "human_verdicts": quality["human_verdicts"], "openjudge_rows": quality["openjudge_rows"]}
        inputs["claw_snapshot"] = directory.name
        rows.extend(claw)
    rows.sort(key=lambda row: (row["task"]["id"], row["trial"]["id"]))
    return rows, {"schema_version": SCHEMA_VERSION, "snapshot_version": SNAPSHOT_VERSION, "sources": sources,
                  "inputs": inputs, "input_sha256": digest(json_text(inputs).encode()),
                  "cross_source_task_family_overlap": "unknown" if claw_root else "not_applicable"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--claw-root", type=Path, help="checkout with a verified P0 export")
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    claw = args.claw_root.resolve() if args.claw_root else None
    protected = [bundle] + ([claw / "outputs/dataset"] if claw else [])
    if any(output.is_relative_to(path) or path.is_relative_to(output) for path in protected):
        parser.error("output must be separate from the bundle and P0 snapshot store")
    try:
        output.mkdir(parents=True, exist_ok=True)
        with (output / ".build.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows, report = build(bundle, claw)
            directory = publish_snapshot(output, rows, report)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        parser.exit(1, f"cross-source build failed: {exc}\n")
    exclusions = len(report["sources"]["swe-bench"]["excluded"])
    print(f"{len(rows)} imported trials; {exclusions} SWE-bench exclusions; snapshot {directory}")
    return int(exclusions > 0)


if __name__ == "__main__":
    raise SystemExit(main())
