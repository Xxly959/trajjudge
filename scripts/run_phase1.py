#!/usr/bin/env python
"""Regenerate reports/phase1.md from cached grader output (stage S7)."""

from __future__ import annotations

import os
import subprocess
import sys

from trajjudge.config import PROJECT_ROOT


def main() -> int:
    """Replay cached graders, then report; never start a paid task or request."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for script, arguments in (("score_trajectories.py", ["--offline"]), ("report.py", [])):
        result = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / script), *arguments],
                                cwd=PROJECT_ROOT, env=env, check=False)
        if result.returncode:
            print(f"phase1 stopped at {script}; restore local artifacts/cache or inspect error rows. No paid fallback was attempted.", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
