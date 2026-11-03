"""Tests for the content-addressed disk cache."""

from __future__ import annotations

from pathlib import Path

from trajjudge.cache import DiskCache, make_key


def test_key_is_stable_and_order_insensitive() -> None:
    first = make_key({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    second = make_key({"messages": [{"role": "user", "content": "hi"}], "model": "m"})

    assert first == second
    assert len(first) == 64


def test_key_changes_when_messages_change() -> None:
    base = {"model": "m"}
    assert make_key({**base, "messages": "a"}) != make_key({**base, "messages": "b"})


def test_put_and_get_roundtrip(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path / "cache")
    key = make_key({"x": 1})

    assert cache.get(key) is None
    path = cache.put(key, {"text": "hello", "tool_calls": []})

    assert path.is_file()
    assert cache.get(key) == {"text": "hello", "tool_calls": []}


def test_corrupt_entry_is_treated_as_miss(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path / "cache")
    key = make_key({"x": 1})
    cache.root.mkdir(parents=True)
    cache.path_for(key).write_text("{not json", encoding="utf-8")

    assert cache.get(key) is None
