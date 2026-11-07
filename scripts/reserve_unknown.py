#!/usr/bin/env python
"""Reconstruct legacy unknown-attempt bounds offline without altering usage records."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from experiment import frozen_traces
import trajjudge.llm as llm
from trajjudge.artifacts import atomic_text
from trajjudge.cache import make_key
from trajjudge.config import load_settings
from trajjudge.judging import JudgeConfig, _grade
from trajjudge.usage import UsageLog, budget_cost, load_pricing, load_reservations, record_id, request_reservation


def main() -> int:
    """Plan by default; --apply records evidence-backed bounds, never invented usage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run_dir = root / "runs/p2-deepseek-flash"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if make_key(manifest["plan"]) != manifest["identity"]:
        raise ValueError("run plan fingerprint mismatch")
    settings = replace(load_settings(require_key=False), judge_model=manifest["plan"]["model"],
                       pricing_file=root / "configs/pricing_p3.yaml")
    prices = load_pricing(settings.pricing_file)
    ledger = UsageLog(settings.usage_log)
    original_bytes = settings.usage_log.read_bytes()
    entries = load_reservations(settings.usage_log)
    records = ledger.read()
    traces = frozen_traces()
    evidence, proposed = [], dict(entries)
    client = llm.LLMClient(settings, offline=True)
    for record in records:
        if record.usage_known or record.cached or record_id(record) in entries or record.raw_usage.get("budget_reservation"):
            continue
        matches = []
        for job in manifest["plan"]["jobs"]:
            cfg = JudgeConfig(**job["config"])
            tag = f"p2/{job['trace_id']}/{job['variant']}/{cfg.name}/{job['repeat_id']}"
            if tag == record.tag:
                matches.append((job, cfg))
        if len(matches) != 1:
            raise ValueError("unknown attempt cannot be uniquely matched to the approved P2 plan")
        job, cfg = matches[0]
        messages = traces[job["trace_id"]]
        if make_key({"messages": messages}) != job["input_sha256"]:
            raise ValueError("frozen input does not match original job")
        captured = []
        original_key = llm.make_key
        def capture(payload):
            if "request" in payload:
                captured.append(payload["request"])
            return original_key(payload)
        llm.make_key = capture
        try:
            _, bridge = asyncio.run(_grade(messages, cfg, client, job["repeat_id"], record.tag))
        finally:
            llm.make_key = original_key
        if len(captured) != 1 or len(bridge.results) != 1 or not bridge.results[0].cached:
            raise ValueError("exact successful-retry cache replay required for reservation evidence")
        retry = [r for r in records if r.tag == record.tag and r.status == "success" and r.usage_known and not r.cached]
        if not retry or record.model != settings.judge_model or record.thinking != cfg.thinking:
            raise ValueError("successful same-tag retry and matching model/thinking required")
        spec = request_reservation(captured[0], prices[record.model])
        spec["evidence"] = {"job_id": make_key(job), "successful_retry_record_id": record_id(retry[-1]),
                            "source": "frozen plan + exact cached retry; retry loop reuses unchanged request"}
        proposed[record_id(record)] = spec
        evidence.append({"record_id": record_id(record), "original_record": record.to_dict(), "reservation": spec})
    if not settings.usage_log.read_bytes().startswith(original_bytes):
        raise ValueError("original ledger prefix changed; refusing overlay")
    accounted = budget_cost(ledger.read(), prices, proposed)
    if accounted is None:
        raise ValueError("some unknown attempts remain unbounded; no paid execution allowed")
    if args.apply:
        for item in evidence:
            path = run_dir / "accounting" / f"{item['record_id']}.json"
            if path.exists() and json.loads(path.read_text()) != item:
                raise ValueError("existing accounting evidence conflicts")
            atomic_text(path, json.dumps(item, indent=2))
        atomic_text(settings.usage_log.with_suffix(".reservations.json"), json.dumps({"schema": 1, "entries": proposed}, indent=2))
    print(json.dumps({"applied": args.apply, "new_reservations": len(evidence),
                      "budget_cost_including_reservations_usd": accounted,
                      "original_usage": "still unknown; ledger prefix preserved",
                      "bounds": [{"record_id": e["record_id"], **{k: e["reservation"][k] for k in
                          ("input_token_bound", "max_output_tokens", "request_sha256")}} for e in evidence]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
