"""Scan Git index and working files without displaying credential values."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

KEY_PATTERN = re.compile(rb"sk-[A-Za-z0-9_\-]{16,}")


def _git(root: Path, *args: str) -> bytes:
    """Read Git data; failures abort the check rather than silently passing."""
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def scan_repository(root: Path) -> list[str]:
    """Return offending paths in staged blobs and nonignored working files."""
    offenders: list[str] = []
    for entry in _git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        blob_id = header.split()[1].decode("ascii")
        if KEY_PATTERN.search(_git(root, "cat-file", "blob", blob_id)):
            offenders.append("index:" + name.decode("utf-8", errors="replace"))
    names = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    for name in sorted(set(names.split(b"\0")) - {b""}):
        relative = name.decode("utf-8")
        path = root / relative
        if path.is_symlink():
            continue
        if path.exists() and path.is_file() and KEY_PATTERN.search(path.read_bytes()):
            offenders.append("worktree:" + relative)
    return sorted(set(offenders))
