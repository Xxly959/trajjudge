"""Blind annotation kit: render traces without any score and manage the label CSV.

The kit never creates, suggests or pre-fills labels. Trace ids are replaced by
random blind ids; the id mapping lives outside the annotation directory.
"""

from __future__ import annotations

import csv
import os
import random
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


def validate_labels(rows: Sequence[Mapping[str, str]], expected: Sequence[str]) -> list[str]:
    """Return human-readable problems: bad labels, missing reasons, unknown or missing ids (blank is allowed while in progress)."""
    problems: list[str] = []
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
    problems += [f"missing row for {b}" for b in expected if (b, "1") not in seen]
    return problems


def relabel_sample(blind: Sequence[str], count: int, *, seed: int) -> list[str]:
    """Choose ``count`` blind ids for the self-consistency re-label round."""
    return sorted(random.Random(seed).sample(sorted(blind), min(count, len(blind))))


def new_seed() -> int:
    """Draw a fresh random seed (used once, then recorded)."""
    return secrets.randbits(32)
