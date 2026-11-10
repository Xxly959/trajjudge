"""Usage accounting and cost estimation.

Every LLM call appends one JSON line to ``outputs/usage/usage.jsonl``. Cached
calls are recorded too (flagged ``cached: true`` with their original token
counts) so that the log explains what happened, while cost summaries count only
requests that actually reached the provider.
"""

from __future__ import annotations

import json
import threading
import math
import os
from .cache import make_key
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One LLM request, successful or served from cache."""

    timestamp: str
    tag: str
    model: str
    thinking: bool
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cached: bool
    status: str = "success"
    usage_known: bool = True
    raw_usage: dict[str, Any] = field(default_factory=dict)
    endpoint: str = "chat.completions"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "timestamp": self.timestamp,
            "tag": self.tag,
            "model": self.model,
            "thinking": self.thinking,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": round(self.latency_ms, 1),
            "cached": self.cached,
            "status": self.status,
            "usage_known": self.usage_known,
            "raw_usage": self.raw_usage,
            "endpoint": self.endpoint,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "UsageRecord":
        """Rebuild a record, rejecting incomplete or invalid billing data."""
        required = {"timestamp", "tag", "model", "thinking", "prompt_tokens", "completion_tokens", "latency_ms", "cached"}
        if not isinstance(raw, Mapping) or not required.issubset(raw):
            raise ValueError("incomplete usage record")
        if any(type(raw[key]) is not int or raw[key] < 0 for key in ("prompt_tokens", "completion_tokens")):
            raise ValueError("invalid token counts")
        if any(type(raw[key]) is not bool for key in ("thinking", "cached")):
            raise ValueError("invalid usage flags")
        if not isinstance(raw["model"], str) or not raw["model"]:
            raise ValueError("missing usage model")
        return cls(
            timestamp=str(raw.get("timestamp", "")),
            tag=str(raw.get("tag", "")),
            model=str(raw.get("model", "")),
            thinking=bool(raw.get("thinking", False)),
            prompt_tokens=int(raw.get("prompt_tokens", 0)),
            completion_tokens=int(raw.get("completion_tokens", 0)),
            latency_ms=float(raw.get("latency_ms", 0.0)),
            cached=bool(raw.get("cached", False)),
            status=str(raw.get("status", "success")),
            usage_known=bool(raw.get("usage_known", True)),
            raw_usage=dict(raw.get("raw_usage") or {}),
            endpoint=str(raw.get("endpoint", "chat.completions")),
        )


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UsageLog:
    """Append-only JSONL usage log."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, record: UsageRecord) -> None:
        """Append ``record`` as one JSON line, creating parent directories (thread-safe)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def read(self) -> list[UsageRecord]:
        """Return every record in file order; malformed lines raise an error."""
        if not self.path.is_file():
            return []
        records: list[UsageRecord] = []
        with self._lock:
            text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(UsageRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
                raise ValueError("usage log is corrupt; reconcile before new requests") from None
        return records


@dataclass(frozen=True, slots=True)
class Price:
    """Provider price in USD per 1M tokens."""

    input_per_mtok: float
    output_per_mtok: float


def load_pricing(path: Path) -> dict[str, Price]:
    """Read the price table; entries with ``null`` prices are omitted."""
    if not Path(path).is_file():
        return {}
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    prices: dict[str, Price] = {}
    for model, entry in (raw.get("models") or {}).items():
        if not isinstance(entry, dict):
            continue
        input_price = entry.get("input_per_mtok")
        output_price = entry.get("output_per_mtok")
        if input_price is None or output_price is None:
            continue
        values = (float(input_price), float(output_price))
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("prices must be finite and nonnegative")
        prices[str(model)] = Price(*values)
    return prices


@dataclass(slots=True)
class UsageSummary:
    """Aggregated token counts and, when prices are known, cost."""

    calls: int = 0
    cached_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = 0.0
    unpriced_models: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens for billable calls."""
        return self.prompt_tokens + self.completion_tokens


def summarize(records: Iterable[UsageRecord], pricing: Mapping[str, Price]) -> UsageSummary:
    """Aggregate records, counting only cache misses toward token totals and cost."""
    summary = UsageSummary()
    unpriced: set[str] = set()
    unknown_usage = False
    cost = Decimal(0)
    for record in records:
        summary.calls += 1
        if record.cached:
            summary.cached_calls += 1
            continue
        if record.endpoint == "models":
            continue
        unknown_usage |= not record.usage_known
        summary.prompt_tokens += record.prompt_tokens
        summary.completion_tokens += record.completion_tokens
        price = pricing.get(record.model)
        if price is None:
            unpriced.add(record.model)
            continue
        cost += (
            Decimal(record.prompt_tokens) * Decimal(str(price.input_per_mtok))
            + Decimal(record.completion_tokens) * Decimal(str(price.output_per_mtok))
        ) / Decimal(1_000_000)
    if unpriced:
        summary.unpriced_models = sorted(unpriced)
        summary.cost_usd = None
    elif unknown_usage:
        summary.cost_usd = None
    elif summary.cost_usd is not None:
        summary.cost_usd = float(cost.quantize(Decimal("0.000001"), rounding=ROUND_CEILING))
    return summary


def record_id(record: UsageRecord) -> str:
    """Fingerprint an unchanged ledger record for an external budget reservation."""
    return make_key(record.to_dict())


def load_reservations(usage_path: Path) -> dict[str, Any]:
    """Read the optional reservation overlay; malformed evidence blocks paid work."""
    path = usage_path.with_suffix(".reservations.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if data.get("schema") != 1 or not isinstance(data.get("entries"), dict):
        raise ValueError("invalid budget reservation overlay")
    return data["entries"]


def request_reservation(request: Mapping[str, Any], price: Price) -> dict[str, Any]:
    """Record the same conservative bound as the request guard, never actual usage."""
    from .cache import canonical_json
    return {"basis": "request_byte_bound_v1", "request_sha256": make_key(request),
            "input_token_bound": len(canonical_json(request).encode("utf-8")) + 4096,
            "max_output_tokens": request["max_tokens"], "input_per_mtok": price.input_per_mtok,
            "output_per_mtok": price.output_per_mtok}


def budget_cost(records: Iterable[UsageRecord], pricing: Mapping[str, Price],
                reservations: Mapping[str, Any] | None = None) -> float | None:
    """Return known conservative cost plus documented unknown-attempt reservations.

    This is a spending guard, not an invoice or recovered token usage. ``summarize``
    continues to report actual accounting unknown. Uncovered or invalid unknowns
    still return ``None``. Stored/current prices use the larger rate.
    """
    records = list(records)
    known = summarize([r for r in records if r.usage_known], pricing).cost_usd
    if known is None:
        return None
    total = Decimal(str(known))
    for row in records:
        if row.cached or row.endpoint == "models" or row.usage_known:
            continue
        spec = row.raw_usage.get("budget_reservation", (reservations or {}).get(record_id(row)))
        if not isinstance(spec, dict) or spec.get("basis") != "request_byte_bound_v1" or row.model not in pricing:
            return None
        digest = spec.get("request_sha256", "")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return None
        inputs, outputs = spec.get("input_token_bound"), spec.get("max_output_tokens")
        if any(type(v) is not int or v <= 0 for v in (inputs, outputs)):
            return None
        rates = [spec.get("input_per_mtok"), spec.get("output_per_mtok")]
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in rates):
            return None
        price = pricing[row.model]
        total += (Decimal(inputs) * Decimal(str(max(price.input_per_mtok, rates[0])))
                  + Decimal(outputs) * Decimal(str(max(price.output_per_mtok, rates[1])))) / Decimal(1_000_000)
    return float(total.quantize(Decimal("0.000001"), rounding=ROUND_CEILING))
