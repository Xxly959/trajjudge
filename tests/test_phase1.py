"""The public phase1 entry may only use offline scoring and local reporting."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest


@pytest.mark.parametrize("scoring_code", [0, 1])
def test_phase1_forces_offline_and_stops_after_failed_scoring(monkeypatch: pytest.MonkeyPatch, scoring_code: int) -> None:
    from scripts import run_phase1
    calls: list[list[str]] = []
    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, scoring_code if len(calls) == 1 else 0)
    monkeypatch.setattr(run_phase1.subprocess, "run", run)
    assert run_phase1.main() == scoring_code
    assert calls[0][-1] == "--offline" and "score_trajectories.py" in calls[0][-2]
    assert len(calls) == (2 if scoring_code == 0 else 1)
    if scoring_code == 0:
        assert calls[1][-1].endswith("report.py")
