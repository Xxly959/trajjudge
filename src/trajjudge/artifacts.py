"""Resolve portable local evidence without falling back to another checkout."""

from __future__ import annotations

from pathlib import Path
import os
import tempfile


def atomic_text(path: Path, text: str) -> None:
    """Replace a text artifact atomically, preserving its old value on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def artifact_path(value: str, project_root: Path) -> Path:
    """Map a legacy absolute outputs path into the current project's outputs."""
    parts = Path(value).parts
    if "outputs" not in parts:
        raise ValueError("evidence must be inside the local outputs directory")
    relative = Path(*parts[parts.index("outputs"):])
    root = (project_root / "outputs").resolve()
    candidate = (project_root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("local evidence is missing or escapes outputs; restore artifacts here")
    return candidate
