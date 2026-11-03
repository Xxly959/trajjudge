"""trajjudge — reliability and prompt-injection audit of agent trajectory graders.

Phase 1 scope: connect OpenJudge graders to Claw-Eval trajectories, run a small
end-to-end sample with DeepSeek as the only provider, and publish a v0 report.
Stability and injection experiments belong to phase 2 and are intentionally
absent from this package.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
