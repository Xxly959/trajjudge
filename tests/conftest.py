"""Shared fixtures. Every test runs offline: no network, no real credentials."""

from __future__ import annotations

from pathlib import Path

import pytest

from trajjudge.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at temporary cache and usage paths."""
    (tmp_path / "pricing.yaml").write_text("models:\n  judge-test:\n    input_per_mtok: 1\n    output_per_mtok: 2\n")
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


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if any offline test attempts a network connection."""
    import socket
    from typing import Any
    def deny(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network is forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
