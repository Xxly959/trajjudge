"""Blind annotation kit: render traces without any score and manage the label CSV.

The kit never creates, suggests or pre-fills labels. Trace ids are replaced by
random blind ids; the id mapping lives outside the annotation directory.
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
import secrets
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

FIELDS = ("blind_id", "label", "reason", "annotated_at", "round")
LABELS = ("pass", "fail")
MAX_BLOCK_CHARS = 4000


def blind_ids(trace_ids: Sequence[str], *, seed: int) -> dict[str, str]:
    """Map each trace id to a distinct random blind id (``B`` + 6 hex), order-independent of input."""
    rng = random.Random(seed)
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for trace_id in sorted(trace_ids):
        while (blind := f"B{rng.getrandbits(24):06x}") in used:
            pass
        used.add(blind)
        mapping[trace_id] = blind
    return mapping


def _clip(text: str, limit: int | None = MAX_BLOCK_CHARS) -> str:
    return text if limit is None or len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more characters omitted in this view]"


def render_trace(messages: Sequence[Mapping[str, Any]], *, prompt_criteria: str | None = None, blind_id: str,
                 max_block_chars: int | None = MAX_BLOCK_CHARS) -> str:
    """Render adapted OpenAI messages as Markdown. No scores, model names or trace ids are shown."""
    lines = [f"# Trace {blind_id}", ""]
    if prompt_criteria:
        lines += ["## Task criteria (written by the benchmark authors)", "", _clip(prompt_criteria, max_block_chars), ""]
    lines += ["## Conversation", ""]
    for index, message in enumerate(messages):
        role = message.get("role", "?")
        if role == "tool":
            lines += [f"### [{index}] tool result ({message.get('name', '?')})", "", "```", _clip(str(message.get("content", "")), max_block_chars), "```", ""]
            continue
        lines.append(f"### [{index}] {role}")
        if message.get("content"):
            lines += ["", _clip(str(message["content"]), max_block_chars)]
        for call in message.get("tool_calls", []) or []:
            fn = call.get("function", {})
            lines += ["", f"tool call `{fn.get('name')}` args: `{_clip(str(fn.get('arguments')), None if max_block_chars is None else 800)}`"]
        lines.append("")
    return "\n".join(lines)


def write_template(path: Path, blind: Sequence[str]) -> None:
    """Create an empty label CSV with one row per blind id (label/reason left blank)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for blind_id in blind:
            writer.writerow({"blind_id": blind_id, "round": "1"})


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read the label CSV."""
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save_labels(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    """Atomically save owner-entered labels; preserve the old file on failure."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_labels(rows: Sequence[Mapping[str, str]], expected: Sequence[str], *,
                    excluded: Sequence[tuple[str, str]] = (),
                    evidence: Mapping[str, Sequence[int]] | None = None) -> list[str]:
    """Return human-readable problems: bad labels, missing reasons, unknown or missing ids (blank is allowed while in progress).

    ``excluded`` holds (blind_id, round) pairs retired by the owner; an excluded row
    must stay blank, because labeling it would silently reintroduce retired evidence.
    ``evidence`` maps blind_id to the message indices a round-2 reason may cite.
    """
    problems: list[str] = []
    retired = {(b, str(r)) for b, r in excluded}
    seen = {(r["blind_id"], r.get("round", "1")) for r in rows}
    problems += [f"duplicate row for {key[0]} round {key[1]}" for key, count in
                 Counter((r["blind_id"], r.get("round", "1")) for r in rows).items() if count > 1]
    for row in rows:
        if row["blind_id"] not in expected:
            problems.append(f"unknown blind_id {row['blind_id']}")
        if row["label"] and row["label"] not in LABELS:
            problems.append(f"{row['blind_id']}: label must be one of {LABELS}")
        if row["label"] and not row["reason"].strip():
            problems.append(f"{row['blind_id']}: one-line reason is required")
        if (row["blind_id"], str(row.get("round", "1"))) in retired and row["label"]:
            problems.append(f"{row['blind_id']}: excluded row carries a label; reinstate it before labeling")
        if row["label"] and evidence is not None and row["blind_id"] in evidence:
            problems += [f"{row['blind_id']}: {p}" for p in evidence_problems(row["reason"], evidence[row["blind_id"]])]
    problems += [f"missing row for {b}" for b in expected if (b, "1") not in seen]
    return problems


def relabel_sample(blind: Sequence[str], count: int, *, seed: int) -> list[str]:
    """Choose ``count`` blind ids for the self-consistency re-label round."""
    return sorted(random.Random(seed).sample(sorted(blind), min(count, len(blind))))


def new_seed() -> int:
    """Draw a fresh random seed (used once, then recorded)."""
    return secrets.randbits(32)


UNINFORMATIVE_REASONS = {"ok", "okay", "正确", "合理", "好", "好的", "可以", "通过", "没问题", "无", "yes", "pass"}
CITATION_RE = re.compile(r"\[(\d+)\]")


def reason_warnings(reason: str) -> list[str]:
    """Advisory only: a terse reason is weak evidence, not an invalid label."""
    text = (reason or "").strip()
    out = []
    if len(text) <= 4:
        out.append("reason is 4 characters or fewer")
    if text.lower() in UNINFORMATIVE_REASONS:
        out.append("reason is a generic phrase that records no deciding evidence")
    return out


def message_indices(messages: Sequence[Mapping[str, Any]]) -> list[int]:
    """Indices a reason can cite; they match the ``### [i] role`` headings in the rendered view."""
    return list(range(len(messages)))


def evidence_problems(reason: str, indices: Sequence[int]) -> list[str]:
    """Round 2 requires a citation to a concrete message, so a verdict cannot rest on impression."""
    cited = [int(n) for n in CITATION_RE.findall(reason or "")]
    if not cited:
        return ["round 2 reason must cite at least one message index like [3]"]
    unknown = sorted({n for n in cited if n not in set(indices)})
    return [f"reason cites message(s) {unknown} that do not exist in this trace"] if unknown else []


def read_exclusions(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Replay the append-only exclusion log; the last action per (blind_id, round) wins."""
    state: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.is_file():
        return state
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = (record["blind_id"], str(record.get("round", "1")))
        if record["action"] == "exclude":
            state[key] = record
        else:
            state.pop(key, None)
    return state


def append_exclusion(path: Path, record: Mapping[str, Any]) -> None:
    """Append one audit record; nothing is ever rewritten or deleted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(record), ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def exclude_row(log: Path, rows: Sequence[Mapping[str, str]], blind_id: str, reason: str, *,
                round_id: str = "1", now: str) -> dict[str, Any]:
    """Explicitly retire an unresolved item. A labeled row can never be excluded."""
    if not (reason or "").strip():
        raise ValueError("an exclusion requires a reason")
    matching = [r for r in rows if r["blind_id"] == blind_id and str(r.get("round", "1")) == round_id]
    if not matching:
        raise ValueError(f"no round {round_id} row for {blind_id}")
    if matching[0]["label"]:
        raise ValueError(f"{blind_id} already carries a label; excluding it would discard evidence")
    if (blind_id, round_id) in read_exclusions(log):
        raise ValueError(f"{blind_id} round {round_id} is already excluded")
    record = {"action": "exclude", "blind_id": blind_id, "round": round_id,
              "reason": reason.strip(), "at": now}
    append_exclusion(log, record)
    return record


def reinstate_row(log: Path, blind_id: str, reason: str, *, round_id: str = "1", now: str) -> dict[str, Any]:
    """Undo an exclusion, keeping both the original and the undo in the audit log."""
    if not (reason or "").strip():
        raise ValueError("a reinstate requires a reason")
    if (blind_id, round_id) not in read_exclusions(log):
        raise ValueError(f"{blind_id} round {round_id} is not excluded")
    record = {"action": "reinstate", "blind_id": blind_id, "round": round_id,
              "reason": reason.strip(), "at": now}
    append_exclusion(log, record)
    return record


def round2_blind_ids(round1: Sequence[str], *, seed: int) -> dict[str, str]:
    """Fresh ids for the re-label round, disjoint from round 1 so no label can be recalled by id."""
    rng = random.Random(seed)
    taken = set(round1)
    mapping: dict[str, str] = {}
    for blind_id in sorted(round1):
        while (fresh := f"R{rng.getrandbits(24):06x}") in taken:
            pass
        taken.add(fresh)
        mapping[blind_id] = fresh
    return mapping
