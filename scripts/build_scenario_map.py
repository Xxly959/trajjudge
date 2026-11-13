"""Group Claw-Eval task_ids into language-independent scenarios.

Read-only against the upstream checkout. Two tasks share a scenario when their
language-independent structure matches: tools, services, environment, scoring
component names/weights/checks, safety checks and fixture data shape. Natural
language text (prompt, descriptions, rubric, reference solution) is excluded
because translation copies differ only there.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

TEXT_KEYS = {
    "description", "prompt", "text", "judge_rubric", "reference_solution",
    "task_name", "language", "reason", "comment", "notes", "title", "summary", "help",
}
PATH_RE = re.compile(r"tasks/T\d+(?:zh|en)?_[A-Za-z0-9_]+")


def _strip_text(value: Any) -> Any:
    """Drop natural-language fields anywhere in a structure, including nested schemas."""
    if isinstance(value, dict):
        return {k: _strip_text(v) for k, v in value.items() if k not in TEXT_KEYS}
    if isinstance(value, list):
        return [_strip_text(v) for v in value]
    return value


def _strip_paths(value: Any) -> Any:
    if isinstance(value, str):
        return PATH_RE.sub("tasks/<TASK>", value)
    if isinstance(value, dict):
        return {k: _strip_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_paths(v) for v in value]
    return value


def _normalize(value: Any) -> Any:
    return _strip_paths(_strip_text(value))


def _check_signature(check: dict[str, Any], *, with_keywords: bool) -> tuple:
    kind = check.get("type")
    if kind == "tool_called":
        return (kind, check.get("tool_name"), check.get("min_calls"))
    if kind == "min_length":
        return (kind, check.get("field"), check.get("min_length"))
    if kind == "keywords_present":
        if not with_keywords:
            return (kind, None)
        return (kind, tuple(sorted((str(k) for k in check.get("keywords") or []))))
    return (kind,)


def structure_fingerprint(task: dict[str, Any], *, with_keywords: bool = True) -> str:
    """Language-independent structural fingerprint of a task definition."""
    services = sorted(
        (s.get("name"), s.get("port"), _normalize(s.get("command")))
        for s in task.get("services") or []
    )
    tools = sorted(t.get("name") for t in task.get("tools") or [])
    schemas = sorted(
        (t.get("name"), json.dumps(_normalize(t.get("input_schema")), sort_keys=True))
        for t in task.get("tools") or []
    )
    endpoints = sorted(
        (e.get("tool_name"), e.get("method"), _normalize(e.get("url")))
        for e in task.get("tool_endpoints") or []
    )
    scoring = tuple(
        (c.get("name"), c.get("weight"), _check_signature(c.get("check") or {}, with_keywords=with_keywords))
        for c in task.get("scoring_components") or []
    )
    safety = tuple(sorted((s.get("type"), s.get("tool_name")) for s in task.get("safety_checks") or []))
    dimensions = tuple(sorted(
        d.get("name") if isinstance(d, dict) else str(d)
        for d in task.get("primary_dimensions") or []
    ))
    env = task.get("environment") or {}
    payload = {
        "category": task.get("category"),
        "difficulty": task.get("difficulty"),
        "services": services,
        "tools": tools,
        "schemas": schemas,
        "endpoints": endpoints,
        "scoring": scoring,
        "safety": safety,
        "dimensions": dimensions,
        "timeout": env.get("timeout_seconds"),
        "max_turns": env.get("max_turns"),
        "sandbox_files": len(task.get("sandbox_files") or []),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _shape(value: Any) -> Any:
    """Fixture data shape: keys, lengths and numbers, with free text removed."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape(v) for v in value]
    if isinstance(value, str):
        return "<str>"
    return value


def fixture_evidence(task_dir: Path) -> dict[str, Any]:
    files = sorted(p for p in (task_dir / "fixtures").rglob("*") if p.is_file())
    content, shape = {}, {}
    for p in files:
        rel = str(p.relative_to(task_dir))
        raw = p.read_bytes()
        content[rel] = hashlib.sha256(raw).hexdigest()[:16]
        try:
            shape[rel] = hashlib.sha256(
                json.dumps(_shape(json.loads(raw)), sort_keys=True).encode()
            ).hexdigest()[:16]
        except (ValueError, UnicodeDecodeError):
            shape[rel] = content[rel]
    return {
        "files": tuple(sorted(content)),
        "content": content,
        "shape": shape,
        "content_hash": hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16],
        "shape_hash": hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:16],
    }


def suffix(task_id: str) -> str:
    return re.sub(r"^T\d+(?:zh|en)?_", "", task_id)


def build_map(tasks_root: Path, task_ids: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    issues: dict[tuple, dict[str, Any]] = {}

    def flag(ids: list[str], issue: str, recommendation: str) -> None:
        key = (tuple(sorted(ids)), issue)
        issues.setdefault(key, {"task_ids": sorted(ids), "issue": issue, "recommendation": recommendation})

    by_fp: dict[str, list[str]] = defaultdict(list)
    info: dict[str, dict[str, Any]] = {}
    for tid in task_ids:
        task_dir = tasks_root / tid
        path = task_dir / "task.yaml"
        if not path.exists():
            flag([tid], "task.yaml missing", "owner must supply the task definition")
            continue
        task = yaml.safe_load(path.read_text())
        strict = structure_fingerprint(task, with_keywords=True)
        loose = structure_fingerprint(task, with_keywords=False)
        fx = fixture_evidence(task_dir)
        info[tid] = {
            "strict": strict, "loose": loose, "fixtures": fx,
            "language": (task.get("prompt") or {}).get("language"),
            "category": task.get("category"), "difficulty": task.get("difficulty"),
        }
        by_fp[loose].append(tid)

    # Structure is the grouping evidence. A fixture-shape disagreement inside a
    # structural group is flagged, not split: merging is the conservative direction
    # for cluster bootstrap (fewer independent units), and the owner decides.
    groups: dict[str, list[str]] = {fp: sorted(members) for fp, members in by_fp.items()}

    bases: dict[str, str] = {}
    for key, members in groups.items():
        names = {suffix(t) for t in members}
        bases[key] = sorted(names)[0]
        if len(names) > 1:
            flag(members, f"structurally identical but different name suffixes: {sorted(names)}",
                 "owner must confirm whether these are one scenario")

    # A shared name must not pool structurally different tasks into one bootstrap cluster.
    name_counts: dict[str, int] = defaultdict(int)
    for base in bases.values():
        name_counts[base] += 1
    scenario_of: dict[str, str] = {}
    for key in sorted(groups):
        base = bases[key]
        if name_counts[base] > 1:
            flag(groups[key], f"scenario name '{base}' is reused by structurally different tasks",
                 "keep separate: a name suffix alone does not identify a scenario")
            base = f"{base}@{key}"
        scenario_of.update({t: base for t in groups[key]})

    for tid in sorted(info):
        i = info[tid]
        members = sorted(t for t in scenario_of if scenario_of[t] == scenario_of[tid])
        twins = [t for t in members if t != tid]
        if not twins:
            basis = "unique structure fingerprint; no translation twin in corpus"
            fixture_match = "n/a"
        else:
            same_content = all(i["fixtures"]["content_hash"] == info[t]["fixtures"]["content_hash"] for t in twins)
            same_shape = all(i["fixtures"]["shape_hash"] == info[t]["fixtures"]["shape_hash"] for t in twins)
            same_strict = all(i["strict"] == info[t]["strict"] for t in twins)
            langs = sorted({str(i["language"])} | {str(info[t]["language"]) for t in twins})
            fixture_match = "identical" if same_content else ("same-shape-different-text" if same_shape else "different")
            basis = (
                f"same tools/services/schemas/scoring/safety structure as {','.join(twins)}; "
                f"languages={langs}; keywords_identical={same_strict}; fixtures={fixture_match}"
            )
            if not same_strict:
                flag(members, "keywords_present lists differ between translation copies",
                     "merge: keyword lists are translated, structure agrees")
            if not same_shape:
                flag(members, "fixture data shape differs between translation copies",
                     "owner confirmation required: inspect the differing fixture before merging")
        records.append({
            "task_id": tid,
            "scenario_id": scenario_of[tid],
            "basis": basis,
            "language": i["language"],
            "category": i["category"],
            "difficulty": i["difficulty"],
            "structure_fingerprint": i["loose"],
            "fixture_content_hash": i["fixtures"]["content_hash"],
            "fixture_shape_hash": i["fixtures"]["shape_hash"],
            "fixture_match": fixture_match,
            "scenario_size": len(members),
        })
    return records, [issues[k] for k in sorted(issues)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks-root", type=Path, default=Path("../claw-eval/tasks"))
    ap.add_argument("--task-ids", type=Path, required=True, help="JSON list of task_ids")
    ap.add_argument("--out", type=Path, default=Path("reports/scenario_map.csv"))
    ap.add_argument("--problems-out", type=Path, default=Path("reports/scenario_map_uncertain.json"))
    args = ap.parse_args()

    task_ids = json.loads(args.task_ids.read_text())
    records, problems = build_map(args.tasks_root, task_ids)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    args.problems_out.write_text(json.dumps(problems, ensure_ascii=False, indent=2))
    scenarios = {r["scenario_id"] for r in records}
    print(f"task_ids={len(records)} scenarios={len(scenarios)} uncertain={len(problems)}")
    print(f"wrote {args.out} and {args.problems_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())