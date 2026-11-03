"""Shared fixtures. Every test runs offline: no network, no real credentials."""

from __future__ import annotations

from pathlib import Path

import pytest

from trajjudge.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at temporary cache and usage paths."""
    return Settings(
        api_key="unit-test-key",
        base_url="https://example.invalid",
        judge_model="judge-test",
        agent_model="agent-test",
        judge_thinking=False,
        agent_thinking=False,
        cache_dir=tmp_path / "cache",
        usage_log=tmp_path / "usage" / "usage.jsonl",
        pricing_file=tmp_path / "pricing.yaml",
    )
