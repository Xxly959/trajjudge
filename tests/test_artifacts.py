"""Moved evidence must stay in the current clone instead of using host files."""

from pathlib import Path

import pytest

from trajjudge.artifacts import artifact_path


def test_old_file_is_not_a_fallback_when_local_copy_is_missing(tmp_path: Path) -> None:
    old = tmp_path / "old" / "outputs" / "trace.jsonl"
    old.parent.mkdir(parents=True)
    old.write_text("{}\n")
    with pytest.raises(ValueError, match="local evidence"):
        artifact_path(str(old), tmp_path / "new")


def test_evidence_symlink_cannot_escape_current_outputs(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()
    external = tmp_path / "external.jsonl"
    external.write_text("{}\n")
    (tmp_path / "outputs" / "trace.jsonl").symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        artifact_path("outputs/trace.jsonl", tmp_path)
