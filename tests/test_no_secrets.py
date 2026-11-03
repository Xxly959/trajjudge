"""Guard against committing credentials.

Scans every git-tracked file (falling back to a directory walk when git is not
available) for provider-looking keys, and asserts that ``.env`` is ignored.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
SKIP_DIRS = {".git", ".venvs", ".venv", ".cache", "outputs", "__pycache__", ".pytest_cache"}


def _tracked_files() -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return [
            path
            for path in REPO_ROOT.rglob("*")
            if path.is_file() and not SKIP_DIRS.intersection(path.parts)
        ]
    return [REPO_ROOT / name for name in output.split("\0") if name]


def test_no_provider_keys_in_tracked_files() -> None:
    offenders: list[str] = []
    for path in _tracked_files():
        if path.name == ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if KEY_PATTERN.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == [], f"possible API keys committed in: {offenders}"


def test_dotenv_is_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        pytest.skip("git not available in this environment")
    assert result.returncode == 0, ".env must be git-ignored"
