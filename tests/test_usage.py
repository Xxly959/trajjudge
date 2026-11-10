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


def test_conservative_cost_rounding_never_rounds_down() -> None:
    pricing = {"m": Price(input_per_mtok=0.3, output_per_mtok=1.2)}
    result = summarize([_record(prompt=493, completion=69), _record(prompt=504, completion=38)], pricing)
    assert result.cost_usd == 0.000428


def test_unknown_reservation_does_not_fabricate_actual_usage() -> None:
    from dataclasses import replace
    from trajjudge.usage import budget_cost, record_id
    record = replace(_record(prompt=0, completion=0), usage_known=False, status="unknown")
    price = {"m": Price(1., 2.)}
    reservation = {"basis": "request_byte_bound_v1", "request_sha256": "a" * 64,
                   "input_token_bound": 10000, "max_output_tokens": 1000,
                   "input_per_mtok": 1., "output_per_mtok": 2.}
    assert budget_cost([record], price) is None
    assert budget_cost([record], price, {record_id(record): reservation}) == .012
    assert summarize([record], price).cost_usd is None and record.usage_known is False


def test_reservation_rejects_understated_or_mismatched_evidence() -> None:
    from dataclasses import replace
    from trajjudge.usage import budget_cost, record_id
    record = replace(_record(prompt=0, completion=0), usage_known=False)
    reserve = {"basis": "request_byte_bound_v1", "request_sha256": "a" * 64,
               "input_token_bound": 10000, "max_output_tokens": 1000,
               "input_per_mtok": 0., "output_per_mtok": 0.}
    assert budget_cost([record], {"m": Price(1., 2.)}, {"wrong": reserve}) is None
    assert budget_cost([record], {"m": Price(1., 2.)}, {record_id(record): reserve}) == .012
    reserve["max_output_tokens"] = -1
    assert budget_cost([record], {"m": Price(1., 2.)}, {record_id(record): reserve}) is None
