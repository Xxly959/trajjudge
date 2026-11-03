"""Grading pipeline: adapt traces, run graders, write JSONL (stage S6).

One output line per (trace, grader) pair. The schema is deliberately explicit
so that phase-2 analysis can join on it without re-reading the raw traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GradeRecord:
    """One grader verdict on one trace."""

    trace_id: str
    grader: str
    score: float
    reason: str
    judge_model: str
    thinking: bool
    openjudge_commit: str
    timestamp: str
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSONL-serialisable representation."""
        return {
            "trace_id": self.trace_id,
            "grader": self.grader,
            "score": self.score,
            "reason": self.reason,
            "judge_model": self.judge_model,
            "thinking": self.thinking,
            "openjudge_commit": self.openjudge_commit,
            "timestamp": self.timestamp,
            "usage": dict(self.usage),
            "metadata": dict(self.metadata),
        }


def run_graders(*args: Any, **kwargs: Any) -> list[GradeRecord]:
    """Run the four phase-1 graders over every adapted trace.

    Raises:
        NotImplementedError: Always, until stage S6 lands.
    """
    raise NotImplementedError("run_graders lands in stage S6; see docs/DECISIONS.md")
