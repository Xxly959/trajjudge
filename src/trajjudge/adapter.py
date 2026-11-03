"""Claw-Eval trace -> OpenAI messages adapter (implemented in stage S6).

Contract (frozen here so downstream code and tests agree on the shape):

* Input is one Claw-Eval trace JSONL file (append-only events: ``trace_start``,
  ``message``, ``tool_dispatch``, ``audit_snapshot``, ``trace_end``).
* Output is an ordered list of OpenAI chat messages: ``system``, ``user``,
  ``assistant`` (with ``tool_calls``) and ``tool`` (with ``tool_call_id``).
* Assistant ``reasoning_content`` is preserved as a separate field, never
  merged into ``content``.
* Every input event that has no OpenAI equivalent is returned in ``metadata``
  keyed by event index. Silent dropping is a bug, not a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AdaptedTrace:
    """Result of adapting one trace file."""

    trace_id: str
    task_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def adapt_trace(path: Path) -> AdaptedTrace:
    """Adapt the trace at ``path``.

    Raises:
        NotImplementedError: Always, until stage S6 lands.
    """
    raise NotImplementedError("adapt_trace lands in stage S6; see docs/DECISIONS.md")
