"""Resolve portable local evidence without falling back to another checkout."""

from __future__ import annotations

from pathlib import Path


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
