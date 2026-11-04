"""Install declared host requirements into the independent Claw environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
if __name__ == "__main__":
    raise SystemExit(subprocess.run(["uv", "pip", "install", "--python", sys.executable,
        "--cache-dir", str(root / ".cache/uv"), "-r", str(root.parent / "claw-eval/requirements.txt")], env=env).returncode)
