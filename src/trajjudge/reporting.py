"""Deterministic phase-1 reporting from local scores and the actual usage ledger."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter import read_jsonl
from .artifacts import artifact_path
from .config import PROJECT_ROOT
from .usage import UsageLog, UsageRecord, load_pricing, summarize

GRADERS = ("trajectory_accuracy", "trajectory_comprehensive", "action_loop_detection", "observation_information_gain")


@dataclass(frozen=True, slots=True)
class ReportResult:
    """Rendered evidence and whether all required verdicts/accounting are valid."""

    markdown: str
    complete: bool


def _number(value: Any, low: float, high: float) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and low <= value <= high


def _cell(value: str) -> str:
    """Keep identifiers and source notes inside one Markdown table cell."""
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _cost(value: float | None) -> str:
    return "UNKNOWN" if value is None else f"${value:.6f}"


def _digest_value(value: Any) -> Any:
    """Retain nonfinite error evidence as explicit strings in valid JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_nonfinite": str(value)}
    if isinstance(value, dict):
        return {key: _digest_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_digest_value(item) for item in value]
    return value


PHASE1_TAGS = frozenset({"s2", "s3", "s5", "s6"})


def _stage(record: UsageRecord) -> str:
    if record.tag.startswith("s2/"):
        return "S2 probe"
    if record.tag.startswith("s3/"):
        return "S3 weather"
    if record.tag.startswith("s5/"):
        return "S5 framework judge" if record.tag.endswith("/judge") else "S5 agent"
    if record.tag.startswith("s6/"):
        return "S6 OpenJudge"
    return "Other completions"


def generate_report(*, pilot_path: Path, scores_path: Path, usage_path: Path,
                    pricing_path: Path, output_path: Path, project_root: Path = PROJECT_ROOT) -> ReportResult:
    """Join every pilot trace, preserve missing/error results, and price actual IO.

    Malformed or ambiguous provenance is rejected before replacing a report.
    Incomplete verdicts or unknown costs produce a visible incomplete report.
    Cached ledger rows never change its timestamp, totals or evidence digest.
    """
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    tasks = pilot.get("tasks", [])
    if pilot.get("status") != "complete" or not 1 <= len(tasks) <= 3:
        raise ValueError("report requires a completed one-to-three-task pilot")
    traces: dict[str, dict[str, Any]] = {}
    task_ids: set[str] = set()
    for task in tasks:
        path = artifact_path(task["trial"]["trace"], project_root)
        events = read_jsonl(path)
        starts = [row for row in events if row.get("type") == "trace_start"]
        grading = [row for row in events if row.get("type") == "grading_result"]
        if len(starts) != 1 or not grading or not any(row.get("type") == "trace_end" for row in events):
            raise ValueError("native trace identity, completion or framework result is missing")
        trace_id, task_id = starts[0]["trace_id"], task["task_id"]
        if trace_id in traces or task_id in task_ids or starts[0]["task_id"] != task_id:
            raise ValueError("pilot has duplicate or mismatched trace/task identity")
        if any(row.get("trace_id", trace_id) != trace_id for row in events) or grading[-1].get("task_id") != task_id:
            raise ValueError("native trace contains foreign events or grading")
        framework_score = grading[-1].get("task_score")
        if not _number(framework_score, 0, 1) or framework_score != task["trial"].get("task_score"):
            raise ValueError("pilot score disagrees with native grading_result")
        task_ids.add(task_id)
        traces[trace_id] = {"task_id": task_id, "framework_score": framework_score,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "tool_batches": sum(any(block.get("type") == "tool_use" for block in row.get("message", {}).get("content", []) if isinstance(block, dict)) for row in events if row.get("type") == "message" and row.get("message", {}).get("role") == "assistant"),
                            "tool_calls": sum(block.get("type") == "tool_use" for row in events if row.get("type") == "message" and row.get("message", {}).get("role") == "assistant" for block in row["message"].get("content", []) if isinstance(block, dict))}
    rows = read_jsonl(scores_path)
    verdicts: dict[tuple[str, str], dict[str, Any]] = {}
    commits: set[str] = set()
    modes: set[str] = set()
    for row in rows:
        key = row.get("trace_id"), row.get("grader")
        if key[0] not in traces or key[1] not in GRADERS or key in verdicts:
            raise ValueError("duplicate, foreign or unknown grader row")
        required = {"score", "reason", "judge_model", "thinking", "openjudge_commit", "timestamp", "usage", "metadata", "status"}
        if not required <= row.keys():
            raise ValueError("grader row is missing required provenance")
        source, metadata = traces[key[0]], row["metadata"]
        if metadata.get("task_id") != source["task_id"] or metadata.get("official_result", {}).get("task_score") != source["framework_score"]:
            raise ValueError("grader row refers to another task or framework score")
        if metadata.get("source_sha256", source["sha256"]) != source["sha256"]:
            raise ValueError("grader source hash disagrees with native trace")
        if not re.fullmatch(r"[0-9a-f]{40}", row["openjudge_commit"]):
            raise ValueError("invalid OpenJudge commit")
        commits.add(row["openjudge_commit"])
        if key[1] in GRADERS[:2]:
            if not isinstance(row["judge_model"], str) or not row["judge_model"] or type(row["thinking"]) is not bool:
                raise ValueError("model verdict is missing its model or thinking mode")
            if row["thinking"] is not False:
                raise ValueError("the reviewed phase-1 OpenJudge batch requires thinking disabled")
            modes.add(f"{row['judge_model']} / thinking={str(row['thinking']).lower()}")
        elif row["judge_model"] is not None or row["thinking"] is not None:
            raise ValueError("rule verdict must not claim a judge model")
        verdicts[key] = row
    if len(commits) > 1:
        raise ValueError("mixed OpenJudge commits cannot describe one replay batch")
    if len(modes) > 1:
        raise ValueError("mixed model/thinking modes cannot describe one replay batch")
    if not usage_path.is_file():
        raise ValueError("usage ledger is missing; costs cannot be reconstructed")
    ledger = UsageLog(usage_path).read()
    actual = [row for row in ledger if not row.cached and row.endpoint != "models"
              and row.tag.split("/")[0] in PHASE1_TAGS]
    if not actual:
        raise ValueError("usage ledger contains no original completion evidence")
    for row in rows:
        if row["grader"] not in GRADERS[:2] or row["status"] != "ok":
            continue
        tag = f"s6/{row['trace_id']}/{row['grader']}"
        if not any(record.tag == tag and record.model == row["judge_model"] and
                   record.thinking == row["thinking"] and
                   record.prompt_tokens == row["usage"].get("prompt_tokens") and
                   record.completion_tokens == row["usage"].get("completion_tokens") for record in actual):
            raise ValueError("model verdict does not match its original usage evidence")
    pricing = load_pricing(pricing_path)
    total = summarize(actual, pricing)
    pending = usage_path.with_suffix(".pending").exists()
    if pending:
        total.cost_usd = None
    groups: dict[str, list[UsageRecord]] = defaultdict(list)
    for row in actual:
        groups[_stage(row)].append(row)
    issues: list[str] = []
    if total.cost_usd is None:
        issues.append("Accounting is UNKNOWN: missing model prices or unreconciled provider usage.")
        if pending:
            issues.append("A pending accounting marker exists; ledger subtotals do not bound the final bill.")
    elif total.cost_usd > 3:
        issues.append("The conservative stage cost exceeds the USD 3 budget.")
    lines = ["# Phase 1 report v0", "", f"Integration evidence from {len(traces)} small benchmark runs; no human labels, stability or injection experiments.", "",
             f"Paid evidence through: {max(row.timestamp for row in actual)}.", "",
             "## Per-trace results", "",
             "Claw framework scores below were re-evaluated with DeepSeek and are **not leaderboard-comparable official Gemini/Claude labels**. Different scales/rubrics are shown without rescaling or calculating agreement.", "",
             "| Task | Trace ID | Claw framework (0–1) | Accuracy (1–3) | Comprehensive (0–1) | Action loop (0–1) | Observation gain (0–1) |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    valid = 0
    for trace_id, source in traces.items():
        values: list[str] = []
        for name in GRADERS:
            row = verdicts.get((trace_id, name))
            low, high = (1, 3) if name == GRADERS[0] else (0, 1)
            if row is None:
                values.append("MISSING")
                issues.append(f"Missing verdict: {source['task_id']} / {name}.")
            elif row["status"] != "ok" or not _number(row["score"], low, high) or not isinstance(row["reason"], str) or not row["reason"].strip():
                values.append("ERROR")
                issues.append(f"Invalid/error verdict retained: {source['task_id']} / {name}.")
            else:
                values.append(f"{row['score']:.6f}")
                valid += 1
        lines.append("| " + " | ".join([_cell(source["task_id"]), _cell(trace_id), f"{source['framework_score']:.6f}", *values]) + " |")
    expected = len(traces) * len(GRADERS)
    complete = not issues and valid == expected
    lines += ["", f"Status: {'complete' if complete else 'INCOMPLETE'}. Valid verdicts: {valid}/{expected}; retained traces: {len(traces)}.", "",
              "## Tokens and conservative cost", "",
              "| Stage / role | Actual completion attempts | Input tokens | Output tokens | Estimated USD |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for name in sorted(groups):
        summary = summarize(groups[name], pricing)
        lines.append(f"| {name} | {len(groups[name])} | {summary.prompt_tokens} | {summary.completion_tokens} | {_cost(summary.cost_usd)} |")
    lines += [f"| **Phase 1 total** | **{len(actual)}** | **{total.prompt_tokens}** | **{total.completion_tokens}** | **{_cost(total.cost_usd)}** |", "",
              "Prices use peak input cache-miss and output rates. Provider prompt-cache/off-peak discounts may reduce the invoice. Stage rows round upward to six decimals; the total is independently calculated from unrounded ledger amounts.", ""]
    cache_hits = sum(row["usage"].get("cached_calls", 0) for row in rows)
    api_calls = sum(row["usage"].get("api_calls", 0) for row in rows)
    lines += [f"Scoring artifact: {cache_hits} disk-cache hits, {api_calls} actual API attempts. Cached logical tokens and zero-token model discovery are excluded from paid totals. Regenerating this report makes no paid requests.", "",
              "## Provenance and reproduction", "",
              f"- Claw-Eval commit: `{pilot.get('claw_eval_commit', 'UNKNOWN')}`.",
              f"- OpenJudge commit: `{next(iter(commits), 'UNKNOWN')}`.",
              f"- OpenJudge model modes: {', '.join(sorted(modes)) or 'UNKNOWN'}.",
              f"- Pricing SHA-256: `{hashlib.sha256(pricing_path.read_bytes()).hexdigest()}`."]
    stable = {"traces": traces, "verdicts": [{key: row[key] for key in ("trace_id", "grader", "score", "reason", "judge_model", "thinking", "openjudge_commit", "status")} for row in sorted(rows, key=lambda row: (row["trace_id"], row["grader"]))],
              "actual_usage": [row.to_dict() for row in actual]}
    digest = hashlib.sha256(json.dumps(_digest_value(stable), sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    lines += [f"- Stable evidence SHA-256 (native source hashes, verdicts, actual ledger rows): `{digest}`.", "",
              "With the ignored S5 artifacts, full response cache and usage ledger restored under the current project, run `make phase1`. It replays native OpenJudge scoring offline before reporting. Missing cache entries stop execution; no endpoint fallback is allowed. Use `python scripts/report.py` to render existing score artifacts only. See [README](../README.md) for pinned source checkout and separate environment setup.", "",
              "## Runtime differences from the benchmark", ""]
    lines += ["- " + _cell(str(item)) for item in pilot.get("deviations", [])]
    lines += ["- OpenJudge uses JSON-object output with original-schema local validation before callbacks; full step coverage and raw score checks reject malformed verdicts.",
              "- OpenJudge thinking is disabled; the native Claw framework judge retains thinking enabled. No upstream files or original scoring formula were changed.", "",
              "## Known issues and limits", ""]
    lines += ["- " + item for item in issues]
    batches = ", ".join(str(source["tool_batches"]) for source in traces.values())
    calls = ", ".join(str(source["tool_calls"]) for source in traces.values())
    lines += [f"- One provider and {len(traces)} general text tasks, one trial per task; no statistical agreement, cross-provider generalization or reliability conclusion is supported.",
              "- Framework scores use the original task rubric with a different judge model; they are not human labels. The benchmark safety fixtures were preserved, with no new injection experiment.",
              "- Mismatched rubrics and a tiny sample prevent a meaningful correlation claim, even when some scores coincide.",
              f"- Native Comprehensive excludes original system text from its prompt. It measures assistant tool-call batches ({batches} here), not individual tool invocations ({calls}). Its four raw dimensions use 1–5 and the overall score uses 0–1.",
              "- Action-loop and observation-gain rules use word-set/Jaccard overlap (thresholds 1.0 and 0.5); they do not establish semantic correctness, information utility or task success.",
              "- Native trace JSONL lacks initial system text; matching request sidecars supply it. Raw events and unmapped fields remain in adapter metadata. Partial semantic mappings are not scored.",
              "- T002 native judge_calls is empty despite a paid direct judge-client request; the shared ledger includes it. TraceEnd default scores and grading_result efficiency zeros are not used as task outcome/turn-count labels.",
              "- Local non-streaming IO, output caps, timeouts, bounded retries and native mock environments differ from leaderboard execution. The upstream weather example is a smoke fixture, excluded from the per-trace comparison.",
              "- Raw trajectories, request sidecars, response caches and usage are ignored local evidence; a source-only clone can run mocked tests, but offline report regeneration also requires those artifacts.",
              "- Human annotation, repeated-run stability and prompt-injection audits remain future work; none was implemented in phase 1.", ""]
    markdown = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(output_path)
    return ReportResult(markdown, complete)
