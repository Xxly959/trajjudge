"""Lossless adapter and stratified cohort selector for τ-bench (retail / airline) trajectories.

Supports both:
1. Official ``sierra-research/tau-bench`` JSON archives (``historical_trajectories/*.json`` — a list
   of ``{task_id, reward, info, traj, trial}`` dicts, or a wrapper dict with ``results``).
2. Community JSONL archives (e.g. ``AgentSuite/tau-bench-trajectories`` — one JSON object per line
   with ``task_id``, ``reward``, ``traj`` or ``messages``, ``domain``, ``model``, ``trial``).

Strict anti-leakage contract:
* ``messages`` passed to LLM judges contains ONLY the conversation (system policy + user turns +
  assistant turns + tool calls + tool returns), NEVER ``reward``, ``expected_actions``,
  ``expected_outputs``, or database ground truth.
* Ground-truth database verification info is quarantined inside ``privileged_outcome`` so it can be
  used solely for objective scoring (P1-1) and the cross-vendor privileged AI annotator (P1-3).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

_MUTATING_TAU_TOKENS = frozenset({
    "cancel", "modify", "exchange", "return", "update", "book", "send",
    "transfer", "refund", "change", "delete", "create", "add", "remove",
})


@dataclass(frozen=True, slots=True)
class AdaptedTauTrace:
    """One normalized τ-bench trajectory ready for TrajJudge evaluation."""

    trace_id: str
    scenario_id: str
    domain: str
    task_id: str
    trial: int
    agent_model: str
    objective_pass: bool
    reward: float
    messages: list[dict[str, Any]]
    metadata: dict[str, Any]
    privileged_outcome: dict[str, Any]


def _normalize_tool_call(call: Mapping[str, Any], fallback_idx: int) -> dict[str, Any]:
    fn = call.get("function") or {}
    name = str(fn.get("name") or call.get("name") or "unknown")
    raw_args = fn.get("arguments") if "arguments" in fn else call.get("arguments", "{}")
    if isinstance(raw_args, str):
        args_str = raw_args
    else:
        args_str = json.dumps(raw_args, ensure_ascii=False, sort_keys=True)
    call_id = str(call.get("id") or f"tau_call_{fallback_idx}")
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": args_str},
    }


def _normalize_messages(raw_traj: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize τ-bench ``traj`` into clean OpenAI chat messages with zero ground-truth leakage."""
    out: list[dict[str, Any]] = []
    call_counter = 0
    tool_names: list[str] = []
    mutating_calls = 0
    unmapped_roles: list[str] = []

    for msg in raw_traj:
        role = str(msg.get("role") or "").strip().lower()
        if role not in ("system", "user", "assistant", "tool"):
            unmapped_roles.append(role)
            continue
        content = msg.get("content")
        text = "" if content is None else (content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        entry: dict[str, Any] = {"role": role, "content": text}

        if role == "assistant":
            raw_calls = msg.get("tool_calls") or []
            if raw_calls:
                norm_calls = []
                for call in raw_calls:
                    call_counter += 1
                    nc = _normalize_tool_call(call, call_counter)
                    norm_calls.append(nc)
                    t_name = nc["function"]["name"]
                    tool_names.append(t_name)
                    parts = [p for p in re.split(r"[_\-.]+", t_name.lower()) if p]
                    if any(p in _MUTATING_TAU_TOKENS for p in parts):
                        mutating_calls += 1
                entry["tool_calls"] = norm_calls
        elif role == "tool":
            if msg.get("tool_call_id") is not None:
                entry["tool_call_id"] = str(msg["tool_call_id"])
            if msg.get("name") is not None:
                entry["name"] = str(msg["name"])

        out.append(entry)

    meta = {
        "total_messages": len(out),
        "total_tool_calls": len(tool_names),
        "mutating_tool_calls": mutating_calls,
        "unique_tools": sorted(set(tool_names)),
        "has_system_prompt": any(m["role"] == "system" for m in out),
        "unmapped_roles": unmapped_roles,
    }
    return out, meta


def _infer_domain(record: Mapping[str, Any], default_domain: str) -> str:
    if record.get("domain"):
        return str(record["domain"]).strip().lower()
    if record.get("task_name") and str(record["task_name"]).strip().lower() in ("retail", "airline", "telecom"):
        return str(record["task_name"]).strip().lower()
    info = record.get("info") or {}
    if isinstance(info, Mapping) and info.get("domain"):
        return str(info["domain"]).strip().lower()
    traj_text = json.dumps(record.get("traj") or record.get("messages") or [], ensure_ascii=False)[:2000].lower()
    if any(k in traj_text for k in ("reservation", "flight", "airline", "cabin", "baggage")):
        return "airline"
    if any(k in traj_text for k in ("order", "product", "shipping", "retail", "exchange_delivered")):
        return "retail"
    return default_domain


def adapt_taubench_record(
    record: Mapping[str, Any],
    *,
    default_domain: str = "retail",
    default_agent_model: str = "unknown",
    source_file: str = "",
) -> AdaptedTauTrace:
    """Adapt a single τ-bench record (official JSON or AgentSuite JSONL) into ``AdaptedTauTrace``."""
    raw_traj = record.get("traj") if "traj" in record else record.get("messages")
    if not isinstance(raw_traj, list) or not raw_traj:
        raise ValueError("τ-bench record missing non-empty 'traj'/'messages' list")

    meta = record.get("meta") if isinstance(record.get("meta"), Mapping) else {}
    eval_res = record.get("eval_result") if isinstance(record.get("eval_result"), Mapping) else {}

    domain = _infer_domain(record, default_domain)
    raw_task_id = record.get("task_id") if record.get("task_id") is not None else meta.get("task_id")
    task_id = str(raw_task_id) if raw_task_id is not None else ""
    if not task_id or task_id == "None":
        raise ValueError("τ-bench record missing 'task_id'")
    trial = int(record.get("trial", meta.get("trial", 0)) or 0)
    agent_model = str(
        record.get("model")
        or record.get("agent_model")
        or record.get("model_path")
        or default_agent_model
    )

    raw_reward = record.get("reward") if record.get("reward") is not None else eval_res.get("score")
    if raw_reward is None:
        raise ValueError(f"τ-bench record task_id={task_id} missing objective 'reward'")
    reward = float(raw_reward)
    objective_pass = reward >= 1.0 - 1e-9

    messages, msg_meta = _normalize_messages(raw_traj)
    canonical = json.dumps(
        {"domain": domain, "task_id": task_id, "trial": trial, "agent_model": agent_model, "messages": messages},
        sort_keys=True,
        ensure_ascii=False,
    )
    short_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:10]
    trace_id = f"tau_{domain}_{task_id}_t{trial}_{short_hash}"
    scenario_id = f"taubench:{domain}:{task_id}"

    info = record.get("info") if isinstance(record.get("info"), Mapping) else {}
    task_info = (
        info.get("task")
        if isinstance(info.get("task"), Mapping)
        else (meta.get("task_description") if isinstance(meta.get("task_description"), Mapping) else {})
    )
    privileged = {
        "reward": reward,
        "objective_pass": objective_pass,
        "reward_info": (
            info.get("reward_info")
            or meta.get("reward_details")
            or eval_res
            or {k: info[k] for k in ("reward_action", "reward_output") if k in info}
        ),
        "user_instruction": task_info.get("instruction") or record.get("instruction"),
        "expected_actions": task_info.get("actions") or record.get("actions") or [],
        "expected_outputs": task_info.get("outputs") or record.get("outputs") or [],
    }
    metadata = {
        **msg_meta,
        "source_file": source_file,
        "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }
    return AdaptedTauTrace(
        trace_id=trace_id,
        scenario_id=scenario_id,
        domain=domain,
        task_id=task_id,
        trial=trial,
        agent_model=agent_model,
        objective_pass=objective_pass,
        reward=reward,
        messages=messages,
        metadata=metadata,
        privileged_outcome=privileged,
    )


def load_taubench_file(
    path: Path,
    *,
    default_domain: str | None = None,
    default_agent_model: str | None = None,
) -> list[AdaptedTauTrace]:
    """Load a τ-bench JSON or JSONL file into normalized ``AdaptedTauTrace`` objects."""
    stem_lower = path.stem.lower()
    inferred_domain = default_domain or ("airline" if "airline" in stem_lower else "retail")
    inferred_model = default_agent_model or path.stem

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    records: list[Mapping[str, Any]]
    if path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            inferred_domain = str(parsed.get("domain") or inferred_domain)
            inferred_model = str(parsed.get("model") or inferred_model)
            records = parsed["results"]
        else:
            raise ValueError(f"unrecognized τ-bench JSON layout in {path}")

    out: list[AdaptedTauTrace] = []
    for rec in records:
        if not isinstance(rec, Mapping):
            continue
        out.append(
            adapt_taubench_record(
                rec,
                default_domain=inferred_domain,
                default_agent_model=inferred_model,
                source_file=path.name,
            )
        )
    return out


def select_taubench_cohort(
    traces: Sequence[AdaptedTauTrace],
    *,
    target_failures: int = 100,
    target_passes: int = 100,
    min_scenarios: int = 60,
    seed: int = 20261119,
) -> dict[str, Any]:
    """Select a reproducible, scenario-diverse cohort meeting P1-1 scale targets.

    Prioritizes breadth across independent ``scenario_id``s first (1 failure / 1 pass per
    scenario before sampling additional trials from the same scenario) so cluster effective
    sample size is maximized.
    """
    rng = random.Random(seed)
    fails_by_scen: dict[str, list[AdaptedTauTrace]] = defaultdict(list)
    passes_by_scen: dict[str, list[AdaptedTauTrace]] = defaultdict(list)

    for tr in sorted(traces, key=lambda x: (x.scenario_id, x.agent_model, x.trial, x.trace_id)):
        if tr.objective_pass:
            passes_by_scen[tr.scenario_id].append(tr)
        else:
            fails_by_scen[tr.scenario_id].append(tr)

    def _round_robin(by_scen: dict[str, list[AdaptedTauTrace]], target: int) -> list[AdaptedTauTrace]:
        scens = sorted(by_scen)
        rng.shuffle(scens)
        buckets = {s: list(by_scen[s]) for s in scens}
        for s in scens:
            rng.shuffle(buckets[s])
        chosen: list[AdaptedTauTrace] = []
        while len(chosen) < target:
            added = False
            for s in scens:
                if buckets[s] and len(chosen) < target:
                    chosen.append(buckets[s].pop(0))
                    added = True
            if not added:
                break
        return chosen

    chosen_fails = _round_robin(fails_by_scen, target_failures)
    chosen_passes = _round_robin(passes_by_scen, target_passes)
    selected = sorted(chosen_fails + chosen_passes, key=lambda x: x.trace_id)
    unique_scenarios = sorted({t.scenario_id for t in selected})
    by_domain: dict[str, int] = defaultdict(int)
    by_model: dict[str, int] = defaultdict(int)
    for t in selected:
        by_domain[t.domain] += 1
        by_model[t.agent_model] += 1

    return {
        "seed": seed,
        "n_total": len(selected),
        "n_failures": len(chosen_fails),
        "n_passes": len(chosen_passes),
        "n_scenarios": len(unique_scenarios),
        "meets_p1_target": len(chosen_fails) >= target_failures and len(unique_scenarios) >= min_scenarios,
        "by_domain": dict(sorted(by_domain.items())),
        "by_agent_model": dict(sorted(by_model.items())),
        "cohort_sha256": hashlib.sha256(
            json.dumps([t.trace_id for t in selected]).encode("utf-8")
        ).hexdigest(),
        "traces": selected,
    }


def select_best_of_n_tasks(
    traces: Sequence[AdaptedTauTrace],
    *,
    n_candidates: int = 4,
    max_tasks: int = 100,
) -> list[dict[str, Any]]:
    """Group multi-trial τ-bench runs into P2-A Best-of-N reranking tasks (exact N trials per task)."""
    grouped: dict[tuple[str, str], list[AdaptedTauTrace]] = defaultdict(list)
    for tr in sorted(traces, key=lambda x: (x.scenario_id, x.agent_model, x.trial, x.trace_id)):
        grouped[(tr.scenario_id, tr.agent_model)].append(tr)

    tasks: list[dict[str, Any]] = []
    for (scen, model), items in sorted(grouped.items()):
        if len(items) < n_candidates:
            continue
        cands = items[:n_candidates]
        pass_count = sum(1 for c in cands if c.objective_pass)
        tasks.append({
            "scenario_id": scen,
            "agent_model": model,
            "n_candidates": n_candidates,
            "oracle_pass": pass_count > 0,
            "pass_count": pass_count,
            "mixed_outcomes": 0 < pass_count < n_candidates,
            "candidate_trace_ids": [c.trace_id for c in cands],
        })
        if len(tasks) >= max_tasks:
            break
    return tasks
