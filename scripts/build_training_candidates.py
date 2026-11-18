#!/usr/bin/env python3
"""Build local TRL candidates and a screening audit from versioned P2 evidence."""

import argparse
from collections import Counter
from itertools import product
import json
import os
from pathlib import Path
import re
import runpy
import sys
from tempfile import TemporaryDirectory

from build_cross_source import json_document
from build_dataset import digest, json_text


ROOT = Path(__file__).resolve().parents[1] / "tasks/original"
DEFAULT_POLICY = ROOT / "partitions-v1.json"
VERSION = 1
CLAIM = re.compile(r"已完成修改并生成 (?:result\.json|`result\.json`)[。.]?")
NAME = re.compile(r"[a-z][a-z0-9-]*")
KNOWN_ORIGINS = ("constructed_fixture", "model_run")


def read_json(path):
    return json_document(path.read_bytes())


def partition_index(policy):
    if type(policy["version"]) is not int or policy["version"] != VERSION:
        raise ValueError("unsupported partition version")
    families, tasks = set(), {}
    for entry in policy["families"]:
        family, purpose = entry["family"], entry["purpose"]
        if not family.startswith("original:") or family in families or purpose not in {"train", "eval"}:
            raise ValueError(f"invalid or repeated task family: {family}")
        families.add(family)
        if not entry["tasks"]:
            raise ValueError(f"task family has no tasks: {family}")
        for task in entry["tasks"]:
            if not NAME.fullmatch(task) or task in tasks:
                raise ValueError(f"invalid or repeated task assignment: {task}")
            tasks[task] = (family, purpose)
    if not tasks:
        raise ValueError("empty task partition policy")
    return tasks


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_conversation(messages, tools):
    if not isinstance(tools, list):
        raise ValueError("tools must be a list of function schemas")
    schemas = {}
    for tool in tools:
        spec = tool["function"]
        name = spec["name"]
        params = spec["parameters"]
        if (tool["type"] != "function" or not has_text(name) or name in schemas
                or not isinstance(params, dict) or params.get("type") != "object"):
            raise ValueError("invalid or duplicate function schema")
        required = params.get("required", [])
        if not isinstance(required, list) or not all(has_text(key) for key in required):
            raise ValueError("invalid required argument names in function schema")
        schemas[name] = set(required)
    if (not isinstance(messages, list) or not messages or messages[0]["role"] != "user"
            or not has_text(messages[0].get("content"))):
        raise ValueError("complete interaction must start with a user prompt")
    final = messages[-1]
    if final["role"] != "assistant" or final.get("tool_calls") or not has_text(final.get("content")):
        raise ValueError("complete interaction must end with a final assistant response")
    pending, seen = {}, set()
    for message in messages[1:-1]:
        if message["role"] == "assistant" and not pending:
            calls = message.get("tool_calls")
            if not isinstance(calls, list) or not calls:
                raise ValueError("intermediate assistant turn must call a tool")
            for call in calls:
                function = call["function"]
                call_id, name = call["id"], function["name"]
                if call["type"] != "function" or not has_text(call_id) or call_id in seen or name not in schemas:
                    raise ValueError("invalid tool call ID or function")
                arguments = function["arguments"]
                if not isinstance(arguments, dict) or not schemas[name].issubset(arguments):
                    raise ValueError("tool call arguments must be a JSON object containing the required keys")
                seen.add(call_id)
                pending[call_id] = name
        elif message["role"] == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending or message.get("name") != pending[call_id] or not has_text(message.get("content")):
                raise ValueError("tool return must match a pending call ID and function")
            del pending[call_id]
        else:
            raise ValueError("unexpected message or missing tool return")
    if not seen or pending:
        raise ValueError("missing tool return or no tool interaction")


def preference_pair(chosen, rejected):
    if chosen["purpose"] != "train" or rejected["purpose"] != "train":
        return None, "evaluation_family"
    if any(chosen[key] != rejected[key] for key in ("task", "family", "task_version", "instruction_sha256")):
        return None, "different_task"
    if any(chosen[key] != rejected[key] for key in ("environment_sha256", "verifier_version")):
        return None, "different_environment"
    if (chosen["outcome"], rejected["outcome"]) != ("pass", "fail"):
        return None, "incomparable_outcomes"
    if not chosen.get("messages") or not rejected.get("messages"):
        return None, "missing_complete_trajectory"
    prompt = chosen["messages"][:1]
    if prompt != rejected["messages"][:1] or chosen["tools"] != rejected["tools"]:
        return None, "different_prompt_or_tools"
    if chosen["messages"][1:] == rejected["messages"][1:]:
        return None, "identical_completions"
    if chosen["source_id"] == rejected["source_id"] or rejected["reason"] not in {
        "artifact_mismatch", "missing_artifact", "invalid_artifact", "unexpected_exit",
        "missing_error_message", "unexpected_artifact",
    }:
        return None, "incomparable_outcomes"
    return {"prompt": prompt, "chosen": chosen["messages"][1:],
            "rejected": rejected["messages"][1:], "tools": chosen["tools"]}, None


def compare_filters(rows):
    final_selected, verified_selected = [], []
    final_excluded, verified_excluded = Counter(), Counter()
    for row in rows:
        reply = row["final_reply"]
        if reply and CLAIM.fullmatch(reply.strip()):
            final_selected.append(row["source_id"])
        else:
            reason = "unrecognized_claim" if reply else row.get("final_reply_issue") or "missing_final_reply"
            final_excluded[reason] += 1
        if row["outcome"] == "pass":
            verified_selected.append(row["source_id"])
        else:
            verified_excluded["outcome_unknown" if row["outcome"] == "unknown" else "not_verified_pass"] += 1
    return {
        "denominator": len(rows),
        "final_reply_only": {"selected": final_selected, "excluded_by_reason": dict(final_excluded)},
        "verified_outcome": {"selected": verified_selected, "excluded_by_reason": dict(verified_excluded)},
        "selected_by_both": sorted(set(final_selected) & set(verified_selected)),
        "selected_by_final_only": sorted(set(final_selected) - set(verified_selected)),
        "selected_by_outcome_only": sorted(set(verified_selected) - set(final_selected)),
    }


def verified_outcome(run_dir, record, version, expected_cases, expected_artifact, artifact_check):
    source_bytes = (run_dir / "submitted-solution.py").read_bytes()
    if digest(source_bytes) != record["candidate_sha256"] or record["verifier_version"] != version:
        raise ValueError("candidate or verifier hash mismatch")
    raw_checks = (run_dir / "verification/checks.json").read_bytes()
    checks = json_document(raw_checks)
    if (checks["verifier_version"] != version or type(checks["exit"]) is not int
            or type(record["verifier_exit"]) is not int or checks["exit"] != record["verifier_exit"]):
        raise ValueError("verifier summary disagrees with report")
    items = checks["checks"]
    by_id = {check["id"]: check["status"] for check in items}
    failures = {key: status for key, status in by_id.items() if status != "ok"}
    if len(items) != len(by_id) or failures != record["failed_checks"] or record["checks"] != len(items):
        raise ValueError("per-case evidence disagrees with matrix")
    output = run_dir / "verification/submitted-result.json"
    artifact = output.read_bytes() if output.is_file() else None
    if checks["exit"] == 2 or "infrastructure_error" in checks:
        return "unknown", "infrastructure_error", digest(raw_checks), None if artifact is None else digest(artifact)
    if set(by_id) != expected_cases.keys() | {"submitted-artifact"} or checks["exit"] not in (0, 1) or bool(failures) != (checks["exit"] == 1):
        raise ValueError("unexpected check set or verdict")
    actual_artifact_status = artifact_check(output, expected_artifact)
    if by_id["submitted-artifact"] != actual_artifact_status:
        raise ValueError("delivered artifact disagrees with reported check")
    if "candidate_timeout" in failures.values():
        return "unknown", "candidate_timeout", digest(raw_checks), None if artifact is None else digest(artifact)
    for check in items:
        if check["id"] == "submitted-artifact":
            continue
        expected_exit, command, expected = expected_cases[check["id"]]
        if check["command"] != command or check["expected_exit"] != expected_exit or type(check["exit"]) is not int:
            raise ValueError("saved command or exit metadata disagrees with the case")
        case_dir = run_dir / "verification" / check["id"]
        stderr = (case_dir / "stderr.txt").read_bytes()
        status = artifact_check(case_dir / "result.json", expected)
        if check["exit"] != expected_exit:
            status = "unexpected_exit"
        elif expected_exit and not stderr.strip():
            status = "missing_error_message"
        if status != check["status"]:
            raise ValueError("saved case artifact or stderr disagrees with the reported check")
    return ("fail" if failures else "pass", next(iter(failures.values()), "passed_all_checks"),
            digest(raw_checks), None if artifact is None else digest(artifact))


def read_trace(path, row, instruction):
    envelope = read_json(path)
    expected = {key: row[key] for key in ("source_id", "origin", "candidate_sha256", "verifier_version",
                                          "checks_sha256", "artifact_sha256")}
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != VERSION:
        raise ValueError("unsupported trace version")
    if envelope["complete"] is not True:
        raise ValueError("trajectory marked incomplete")
    if any(envelope[key] != value for key, value in expected.items()):
        raise ValueError("trajectory does not reference this candidate and verification evidence")
    messages, tools = envelope["messages"], envelope["tools"]
    validate_conversation(messages, tools)
    if messages[0]["content"] != instruction:
        raise ValueError("trajectory prompt differs from the visible task instruction")
    if row["final_reply"] and row["final_reply"] != messages[-1]["content"].strip():
        raise ValueError("trajectory and saved final reply disagree")
    return messages, tools


def task_rows(evidence, task, family, purpose):
    path = evidence / task
    task_root = ROOT / task
    matrix_data = (path / "matrix.json").read_bytes()
    matrix = json_document(matrix_data)
    instruction_data = (task_root / "instruction.md").read_bytes()
    if matrix["task"] != task or type(matrix["task_version"]) is not int or matrix["task_version"] != VERSION:
        raise ValueError(f"wrong task or version for {task}")
    if matrix["instruction_sha256"] != digest(instruction_data):
        raise ValueError(f"task instruction changed for {task}")
    instruction = instruction_data.decode("utf-8")
    verifier = runpy.run_path(str(ROOT / "verify.py"))
    suite_path = task_root / "cases.py"
    suite = runpy.run_path(str(suite_path))
    version = verifier["verifier_version"](suite_path)
    expected = verifier["canonical"](suite["SUBMITTED_RESULT"])
    max_digits = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        cases = {
            case["id"]: (
                case.get("exit", 0),
                ["solution.py", *case["args"], "result.json"],
                case.get("prior_output") if case.get("exit") else verifier["canonical"](case["expected"]),
            )
            for case in suite["CASES"]
        }
    finally:
        sys.set_int_max_str_digits(max_digits)
    workspace = task_root / "environment/workspace"
    start = {p.relative_to(workspace).as_posix(): digest(p.read_bytes()) for p in workspace.rglob("*") if p.is_file()}
    rows = []
    for name, record in sorted(matrix["matrix"].items()):
        if not NAME.fullmatch(name):
            raise ValueError("invalid submission name")
        run = path / name
        reply = run / "final-reply.txt"
        final_reply, reply_issue = None, None
        try:
            final_reply = reply.read_text(encoding="utf-8").strip() or None
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            reply_issue = "invalid_final_reply"
        origin = record.get("source")
        row = {
            "source_id": f"original:{task}:v{VERSION}:{name}", "task": task, "family": family, "purpose": purpose,
            "task_version": VERSION, "instruction_sha256": matrix["instruction_sha256"], "verifier_version": version,
            "environment_sha256": digest(json_text({"environment": matrix["environment"], "starting_files": start}).encode()),
            "candidate_sha256": record.get("candidate_sha256"), "origin": origin if origin in KNOWN_ORIGINS else "unknown",
            "evidence_path": f"{task}/{name}", "matrix_sha256": digest(matrix_data),
            "final_reply": final_reply, "final_reply_issue": reply_issue,
            "outcome": "unknown", "reason": None, "checks_sha256": None, "artifact_sha256": None,
            "trajectory_sha256": None, "messages": None, "tools": None,
        }
        try:
            if record["starting_files"] != start:
                raise ValueError("starting workspace hash mismatch")
            row["outcome"], row["reason"], row["checks_sha256"], row["artifact_sha256"] = verified_outcome(
                run, record, version, cases, expected, verifier["artifact_check"],
            )
        except FileNotFoundError:
            row["reason"] = "missing_verification_evidence"
        except (OSError, ValueError, KeyError, TypeError):
            row["reason"] = "invalid_verification_evidence"
        trace = run / "trajectory.json"
        if row["origin"] == "unknown":
            row["trajectory_status"] = "unknown_origin"
        elif not trace.is_file():
            row["trajectory_status"] = "missing_trajectory"
        else:
            try:
                row["messages"], row["tools"] = read_trace(trace, row, instruction)
                row["trajectory_sha256"] = digest(trace.read_bytes())
                row["final_reply"] = row["messages"][-1]["content"].strip()
                row["final_reply_issue"] = None
                row["trajectory_status"] = "complete"
            except (OSError, ValueError, KeyError, TypeError) as exc:
                row["trajectory_status"] = "invalid_or_incomplete_trajectory"
                row["trajectory_detail"] = str(exc)
        rows.append(row)
    return rows


def build(evidence, policy_data):
    partitions = partition_index(json_document(policy_data))
    rows = [row for task, (family, purpose) in sorted(partitions.items())
            for row in task_rows(evidence, task, family, purpose)]
    train = [row for row in rows if row["purpose"] == "train"]
    sft, preferences, provenance = [], [], []

    def emit(kind, destination, sample, sources):
        destination.append(sample)
        provenance.append({
            "kind": kind, "row": len(destination), "sample_sha256": digest(json_text(sample).encode()),
            "sources": [{key: row[key] for key in ("source_id", "origin", "family", "task_version", "verifier_version",
                                                  "evidence_path", "environment_sha256", "checks_sha256",
                                                  "artifact_sha256", "trajectory_sha256", "reason")} for row in sources],
        })

    exclusions = Counter()
    for row in rows:
        if row["purpose"] == "eval":
            exclusions["evaluation_family"] += 1
        elif row["outcome"] != "pass":
            exclusions["outcome_unknown" if row["outcome"] == "unknown" else "not_verified_pass"] += 1
        elif row["trajectory_status"] != "complete":
            exclusions[row["trajectory_status"]] += 1
        else:
            emit("sft", sft, {"messages": row["messages"], "tools": row["tools"]}, [row])

    pair_counts = Counter()
    passed = [row for row in train if row["outcome"] == "pass"]
    failed = [row for row in train if row["outcome"] == "fail"]
    for chosen, rejected in product(passed, failed):
        pair, reason = preference_pair(chosen, rejected)
        if pair is None:
            pair_counts[reason] += 1
        else:
            emit("preference", preferences, pair, [chosen, rejected])

    origin_counts = Counter(dict.fromkeys(("constructed_fixture", "model_run", "synthetic_format_fixture"), 0))
    origin_counts.update(row["origin"] for row in rows)
    report = {
        "schema_version": VERSION, "partition_sha256": digest(policy_data),
        "families": {purpose: sorted({f for f, p in partitions.values() if p == purpose}) for purpose in ("train", "eval")},
        "original_tasks": len(partitions), "p2_submissions": len(rows),
        "source_counts": dict(origin_counts),
        "trajectory_counts": dict(Counter(row["trajectory_status"] for row in rows)),
        "cohort": [{k: v for k, v in row.items() if k not in {"messages", "tools", "final_reply"}}
                   | {"final_reply_present": bool(row["final_reply"])} for row in rows],
        "screening_comparison": compare_filters(rows),
        "sft": {"selected": len(sft), "excluded_by_reason": dict(exclusions)},
        "preference": {"selected": len(preferences), "train_pass_fail_combinations": len(passed) * len(failed),
                       "excluded_by_reason": dict(pair_counts)},
    }
    return {"sft.jsonl": sft, "preferences.jsonl": preferences, "provenance.jsonl": provenance}, report


def publish(output, files, report):
    if output.exists() or output.is_symlink():
        raise ValueError("output directory already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".training-stage-", dir=output.parent) as temp:
        stage = Path(temp)
        report["files_sha256"] = {}
        for name, rows in files.items():
            data = "".join(json_text(row) + "\n" for row in rows).encode()
            (stage / name).write_bytes(data)
            report["files_sha256"][name] = digest(data)
        (stage / "quality.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        os.rename(stage, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p2-root", required=True, type=Path)
    parser.add_argument("--partitions", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", required=True, type=Path, help="new directory for versioned candidates")
    args = parser.parse_args()
    try:
        if args.output.resolve().is_relative_to(args.p2_root.resolve()):
            raise ValueError("output must be outside the P2 evidence directory")
        files, report = build(args.p2_root, args.partitions.read_bytes())
        publish(args.output, files, report)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        parser.exit(1, f"candidate build failed: {exc}\n")
    print(f"{report['p2_submissions']} audited submissions; {report['sft']['selected']} SFT rows; "
          f"{report['preference']['selected']} preference rows")


if __name__ == "__main__":
    main()
