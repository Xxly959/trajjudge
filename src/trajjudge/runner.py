"""Serial four-grader scoring with cached LLM IO and explicit error records."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from openjudge.graders.agent import (ActionLoopDetectionGrader, ObservationInformationGainGrader,
    TrajectoryAccuracyGrader, TrajectoryComprehensiveGrader)
from openjudge.graders.schema import GraderScore

from .adapter import AdaptedTrace
from .config import PROJECT_ROOT
from .llm import LLMClient
from .openjudge_bridge import openjudge_model
from .usage import UsageRecord, load_pricing, summarize, utc_now

GRADERS = ("trajectory_accuracy", "trajectory_comprehensive", "action_loop_detection", "observation_information_gain")


@dataclass(slots=True)
class GradeRecord:
    """One verdict; errors have a null score and cannot silently count as zero."""

    trace_id: str
    grader: str
    score: float | None
    reason: str
    judge_model: str | None
    thinking: bool | None
    openjudge_commit: str
    timestamp: str
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    repeat_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "grader": self.grader, "score": self.score,
                "reason": self.reason, "judge_model": self.judge_model, "thinking": self.thinking,
                "openjudge_commit": self.openjudge_commit, "timestamp": self.timestamp,
                "usage": self.usage, "metadata": self.metadata, "status": self.status,
                "repeat_id": self.repeat_id}


def usage_for(records: Sequence[UsageRecord]) -> dict[str, int]:
    """Separate logical usage on replay from tokens billed by actual requests."""
    actual = [row for row in records if not row.cached]
    return {"prompt_tokens": sum(row.prompt_tokens for row in records),
            "completion_tokens": sum(row.completion_tokens for row in records),
            "billable_prompt_tokens": sum(row.prompt_tokens for row in actual),
            "billable_completion_tokens": sum(row.completion_tokens for row in actual),
            "api_calls": len(actual), "cached_calls": sum(row.cached for row in records)}


def validate_verdict(name: str, result: Any, bridge: Any, trace: AdaptedTrace) -> dict[str, Any] | None:
    """Validate source values before accepting normalized/clamped grader scores."""
    if not isinstance(result, GraderScore) or not math.isfinite(result.score) or not result.reason.strip():
        raise ValueError("grader did not return a valid score and reason")
    low, high = (1, 3) if name == "trajectory_accuracy" else (0, 1)
    if not low <= result.score <= high:
        raise ValueError("grader score is outside its documented scale")
    if bridge is None:
        return None
    if len(bridge.results) != 1:
        raise ValueError("expected one model completion per trajectory grader")
    completion = bridge.results[0]
    choices = completion.raw_response.get("choices", [])
    if not choices or choices[0].get("finish_reason") != "stop":
        raise ValueError("judge output is incomplete or filtered")
    raw = json.loads(completion.text)
    if name == "trajectory_accuracy":
        score = raw.get("score")
        if type(score) not in {int, float} or score not in (1, 2, 3) or score != result.score:
            raise ValueError("raw accuracy score is invalid or was clamped")
    else:
        steps = raw.get("step_evaluations")
        count = sum(bool(message.get("tool_calls")) for message in trace.messages if message["role"] == "assistant")
        if not isinstance(steps, list) or len(steps) != count or count == 0:
            raise ValueError("step evaluations do not cover all native assistant tool batches")
        indices = [step.get("step_index") for step in steps]
        if any(type(index) is not int for index in indices) or sorted(indices) != list(range(count)):
            raise ValueError("step indices are missing, duplicated or invalid")
        for step in steps:
            for key in ("contribution_score", "relevance_score", "accuracy_score", "efficiency_score"):
                if type(step.get(key)) is not int or not 1 <= step[key] <= 5:
                    raise ValueError("step scores must be integers from one to five")
            if not isinstance(step.get("step_reason"), str) or not step["step_reason"].strip():
                raise ValueError("step reason is missing")
    return raw


async def _one(trace: AdaptedTrace, name: str, client: LLMClient, commit: str, adapted_path: Path | None) -> GradeRecord:
    llm = name in GRADERS[:2]
    before = len(client.usage_log.read())
    metadata: dict[str, Any] = {
        "task_id": trace.task_id, "official_result": trace.metadata.get("official_result"),
        "source_sha256": trace.metadata.get("source_sha256"),
        "adapter_unmapped_content_count": len(trace.metadata.get("unmapped_content", [])),
        "adapter_metadata_event_count": len(trace.metadata.get("events", {})),
        "system_source": trace.metadata.get("system_source"), "fatal": False,
        "adapted_trace_path": str(adapted_path) if adapted_path else None,
    }
    row = GradeRecord(trace.trace_id, name, None, "", client.settings.judge_model if llm else None,
                      client.settings.judge_thinking if llm else None, commit, utc_now(), metadata=metadata)
    bridge = None
    try:
        if trace.metadata.get("unmapped_content"):
            raise ValueError("semantic mapping is partial; scoring is not permitted")
        if not trace.metadata.get("has_trace_end"):
            raise ValueError("trace is incomplete")
        if llm:
            async with openjudge_model(client, thinking=client.settings.judge_thinking,
                max_tokens=1024 if name == "trajectory_accuracy" else 3072,
                tag=f"s6/{trace.trace_id}/{name}") as (model, bridge):
                grader = TrajectoryAccuracyGrader(model=model) if name == "trajectory_accuracy" else TrajectoryComprehensiveGrader(model=model)
                result = await grader.aevaluate(messages=trace.messages)
                raw = validate_verdict(name, result, bridge, trace)
                metadata["raw_verdict"] = raw
                metadata["wire_observations"] = bridge.observations
        else:
            grader = ActionLoopDetectionGrader() if name == "action_loop_detection" else ObservationInformationGainGrader()
            result = await grader.aevaluate(messages=trace.messages)
            validate_verdict(name, result, None, trace)
        row.score = float(result.score)
        row.reason = result.reason
        metadata["grader_metadata"] = result.metadata
    except Exception as exc:
        row.status = "error"
        row.score = None
        row.reason = str(exc) if isinstance(exc, ValueError) else "grader evaluation failed"
        metadata["error_category"] = type(exc).__name__
    delta = client.usage_log.read()[before:]
    row.usage = usage_for(delta)
    metadata["usage_known"] = all(record.usage_known for record in delta)
    if bridge is not None and bridge.failure is not None:
        metadata["fatal"] = True
        metadata["transport_failure"] = bridge.failure
        row.status, row.score = "error", None
    budget = summarize(client.usage_log.read(), load_pricing(client.settings.pricing_file))
    # A strictly offline cache replay creates no new liability. Keep global live
    # spend protections without invalidating historical verdicts for later runs.
    if llm and not client.offline and (budget.cost_usd is None or budget.cost_usd > client.settings.budget_usd or client._pending_path.exists()):
        metadata["fatal"] = True
        row.status, row.score = "error", None
    return row


def run_graders(traces: Sequence[AdaptedTrace], client: LLMClient, *, output: Path | None = None) -> list[GradeRecord]:
    """Run two model and two rules graders serially; checkpoint every JSONL row.

    A transport/accounting failure stops the batch after its error record. Other
    invalid grader verdicts remain explicit errors rather than numeric scores.
    """
    commit = subprocess.check_output(["git", "-C", str(PROJECT_ROOT.parent / "OpenJudge"), "rev-parse", "HEAD"], text=True).strip()
    if output is not None:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
    async def execute() -> list[GradeRecord]:
        rows: list[GradeRecord] = []
        stream = output.open("w", encoding="utf-8") if output is not None else None
        try:
            for trace in traces:
                adapted_path = None
                if output is not None:
                    target = output.parent / "adapted"
                    target.mkdir(exist_ok=True)
                    adapted_path = target / (hashlib.sha256(trace.trace_id.encode()).hexdigest() + ".json")
                    adapted_path.write_text(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n")
                for name in GRADERS:
                    row = await _one(trace, name, client, commit, adapted_path)
                    rows.append(row)
                    if stream is not None:
                        stream.write(json.dumps(row.to_dict(), ensure_ascii=False, allow_nan=False) + "\n")
                        stream.flush()
                    if row.metadata["fatal"]:
                        return rows
            return rows
        finally:
            if stream is not None:
                stream.close()
    return asyncio.run(execute())
