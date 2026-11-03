"""Tests for usage accounting and cost estimation."""

from __future__ import annotations

from pathlib import Path

import yaml

from trajjudge.usage import (
    Price,
    UsageLog,
    UsageRecord,
    load_pricing,
    summarize,
    utc_now,
)


def _record(*, model: str = "m", prompt: int = 1000, completion: int = 500, cached: bool = False) -> UsageRecord:
    return UsageRecord(
        timestamp=utc_now(),
        tag="test",
        model=model,
        thinking=False,
        prompt_tokens=prompt,
        completion_tokens=completion,
        latency_ms=12.0,
        cached=cached,
    )


def test_usage_log_roundtrip(tmp_path: Path) -> None:
    log = UsageLog(tmp_path / "nested" / "usage.jsonl")
    log.append(_record())
    log.append(_record(cached=True))

    records = log.read()

    assert len(records) == 2
    assert records[1].cached is True
    assert records[0].prompt_tokens == 1000


def test_summarize_skips_cached_calls_for_tokens_and_cost() -> None:
    pricing = {"m": Price(input_per_mtok=1.0, output_per_mtok=2.0)}

    summary = summarize([_record(), _record(cached=True)], pricing)

    assert summary.calls == 2
    assert summary.cached_calls == 1
    assert summary.prompt_tokens == 1000
    assert summary.completion_tokens == 500
    assert summary.cost_usd == 0.002


def test_summarize_reports_unknown_pricing_instead_of_guessing() -> None:
    summary = summarize([_record(model="unpriced")], {})

    assert summary.cost_usd is None
    assert summary.unpriced_models == ["unpriced"]


def test_load_pricing_skips_null_entries(tmp_path: Path) -> None:
    path = tmp_path / "pricing.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "models": {
                    "known": {"input_per_mtok": 0.5, "output_per_mtok": 1.5},
                    "unknown": {"input_per_mtok": None, "output_per_mtok": None},
                }
            }
        ),
        encoding="utf-8",
    )

    prices = load_pricing(path)

    assert set(prices) == {"known"}
    assert prices["known"].input_per_mtok == 0.5
