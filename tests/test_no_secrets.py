"""Credential checks cover both the Git index and working files."""

from __future__ import annotations

import subprocess
from pathlib import Path

from trajjudge.secrets import scan_repository

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_no_provider_keys_in_tracked_files() -> None:
    assert scan_repository(REPO_ROOT) == [], "possible credentials found (values suppressed)"


def test_dotenv_is_ignored() -> None:
    result = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT, capture_output=True)
    assert result.returncode == 0, ".env must be git-ignored"


def test_scanner_checks_index_and_env_example(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    secret = "sk" + "-" + "x" * 24
    example = tmp_path / ".env.example"
    example.write_text("KEY=" + secret)
    subprocess.run(["git", "add", ".env.example"], cwd=tmp_path, check=True)
    example.write_text("KEY=placeholder")
    assert scan_repository(tmp_path) == ["index:.env.example"]
    example.write_text("KEY=" + secret)
    assert scan_repository(tmp_path) == ["index:.env.example", "worktree:.env.example"]


def test_scanner_checks_new_files_before_staging(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "new.txt").write_text("sk" + "-" + "x" * 24)
    assert scan_repository(tmp_path) == ["worktree:new.txt"]
