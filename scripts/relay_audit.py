#!/usr/bin/env python
"""Audit LLM relay vs official endpoint model identities across runs & .cache/llm (Module A4)."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _classify_response_model(req_model: str, resp_model: str | None) -> str:
    if not resp_model:
        return "missing"
    req_l = req_model.lower()
    resp_l = resp_model.lower()
    if resp_l == req_l:
        return "exact_match"
    # Same model family with vendor/channel prefix (e.g. zai-org/GLM-5.3-Flash, codearts/glm-5.3-flash)
    if req_l in resp_l:
        return "same_family_prefixed"
    if req_l.startswith("glm-") and "glm" in resp_l:
        return "same_family_other_glm"
    return "cross_model_mismatch"


def audit_relay_models() -> dict[str, Any]:
    """Audit run rows (request-side judge_model) and .cache/llm (response raw_response.model)."""
    runs_summary: dict[str, Any] = {}
    runs_root = root / "runs"
    if runs_root.is_dir():
        for run_dir in sorted(runs_root.iterdir()):
            if not run_dir.is_dir():
                continue
            rows_dir = run_dir / "rows"
            if not rows_dir.is_dir():
                continue
            req_models: Counter[str] = Counter()
            resp_field_present = 0
            n_rows = 0
            for rf in rows_dir.glob("*.json"):
                n_rows += 1
                row = json.loads(rf.read_text(encoding="utf-8"))
                req_models[str(row.get("judge_model"))] += 1
                if row.get("response_model") or (row.get("raw_response") or {}).get("model"):
                    resp_field_present += 1
            runs_summary[run_dir.name] = {
                "n_rows": n_rows,
                "request_judge_models": dict(sorted(req_models.items())),
                "row_level_response_model_count": resp_field_present,
            }

    cache_root = root / ".cache/llm"
    by_req_prefix: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    by_req_totals: dict[str, Counter[str]] = defaultdict(Counter)
    status_totals: dict[str, Counter[str]] = defaultdict(Counter)
    mismatch_examples: list[dict[str, Any]] = []
    total_cache_files = 0

    if cache_root.is_dir():
        for cf in sorted(cache_root.rglob("*.json")):
            total_cache_files += 1
            try:
                entry = json.loads(cf.read_text(encoding="utf-8"))
            except Exception:
                continue
            req_m = str(entry.get("model") or "unknown")
            tag = str(entry.get("tag") or "")
            prefix = tag.split("/")[0] if "/" in tag else (tag or "untagged")
            raw = entry.get("raw_response")
            resp_m = raw.get("model") if isinstance(raw, dict) else None
            cls = _classify_response_model(req_m, str(resp_m) if resp_m else None)
            resp_label = str(resp_m) if resp_m else "<missing>"
            by_req_prefix[(req_m, prefix)][resp_label] += 1
            by_req_totals[req_m][resp_label] += 1
            status_totals[req_m][cls] += 1
            if cls == "cross_model_mismatch":
                mismatch_examples.append({
                    "requested_model": req_m,
                    "response_model": resp_label,
                    "experiment_prefix": prefix,
                    "tag_type": tag.split("/")[2] if len(tag.split("/")) > 2 else "other",
                })

    by_experiment: list[dict[str, Any]] = []
    for (req_m, prefix), cnt in sorted(by_req_prefix.items()):
        total = sum(cnt.values())
        cls_counts: Counter[str] = Counter()
        for rm, c in cnt.items():
            cls_counts[_classify_response_model(req_m, None if rm == "<missing>" else rm)] += c
        by_experiment.append({
            "requested_model": req_m,
            "experiment_prefix": prefix,
            "total_cached_calls": total,
            "response_models": dict(sorted(cnt.items())),
            "classification": dict(sorted(cls_counts.items())),
        })

    # Aggregate mismatches without trace_ids
    mismatch_summary: dict[str, int] = dict(
        Counter(f"{m['experiment_prefix']}|{m['requested_model']}->{m['response_model']}" for m in mismatch_examples)
    )

    report = {
        "generated_at": _utc_now(),
        "audit_note": (
            "Run row JSON files record only request-side `judge_model` (response_model=0 across historical runs); "
            "actual HTTP response `model` identity is audited directly from `.cache/llm/` `raw_response.model`."
        ),
        "total_cache_entries_scanned": total_cache_files,
        "by_requested_model": {
            m: {
                "total": sum(cnt.values()),
                "response_models": dict(sorted(cnt.items())),
                "classification": dict(sorted(status_totals[m].items())),
            }
            for m, cnt in sorted(by_req_totals.items())
        },
        "by_experiment": by_experiment,
        "cross_model_mismatches": {
            "total_mismatches": len(mismatch_examples),
            "summary_by_experiment_and_model": mismatch_summary,
        },
        "official_direct_control": {
            "models": ["deepseek-flash", "deepseek-v4-pro"],
            "note": "Official api.deepseek.com calls serve as direct-endpoint control without third-party relay routing.",
        },
        "runs_row_level_audit": runs_summary,
    }
    atomic_text(root / "reports/relay_audit.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main() -> int:
    rep = audit_relay_models()
    print(json.dumps({
        "total_cache_entries_scanned": rep["total_cache_entries_scanned"],
        "by_requested_model": {k: v["classification"] for k, v in rep["by_requested_model"].items()},
        "cross_model_mismatches": rep["cross_model_mismatches"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
