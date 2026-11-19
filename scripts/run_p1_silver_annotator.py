#!/usr/bin/env python
"""P1-3 Cross-Vendor Privileged AI Annotator (Silver Label — strictly auxiliary, never gold).

Anti-circularity rules (PREREG_v3 §3):
1. Must use a DIFFERENT model vendor from the primary judged DeepSeek models (e.g., ``qwen`` or ``glm``).
2. Receives privileged task truth (``privileged_outcome``: expected actions, outputs, reward breakdown)
   that NO tested trajectory judge ever sees.
3. Used ONLY for:
   - ``claw48``: cross-checking the 48 human-labeled Claw-Eval trajectories and exporting disagreements
     for human adjudication (``round3_adjudicated``);
   - ``taubench_blindspots``: auditing objectively passing τ-bench trajectories (``reward == 1.0``)
     for process/policy blind spots of executable DB checks (exporting 20 samples for human review).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.config import load_provider_settings  # noqa: E402
from trajjudge.grounded_judge import extract_evidence_ledger  # noqa: E402
from trajjudge.llm import LLMClient, LLMError  # noqa: E402
from trajjudge.usage import load_pricing, utc_now  # noqa: E402

OUT_DIR = root / "outputs/p1_silver"

PRIVILEGED_ANNOTATOR_PROMPT = """You are a Privileged Senior Benchmark Annotator producing a SILVER LABEL audit.
Unlike blind trajectory judges, you have access to PRIVILEGED GROUND-TRUTH CONTEXT (task instructions, expected actions, and objective verification metadata).

Follow this strict decision tree:
1. Check whether the agent satisfied every explicit user requirement and domain policy rule (including obtaining explicit confirmation before irreversible/mutating actions).
2. Check whether executed tool calls match the privileged expected actions and whether reported facts accurately reflect tool returns.
3. Check for process defects that DB-only checks might miss: unauthorized side effects, policy violations, hallucinated claims, or unnecessary/harmful mutations.

Return ONLY one JSON object:
{
  "silver_label": "pass | fail",
  "primary_defect_type": "none | unauthorized_side_effect | policy_violation | missing_action | wrong_arguments | hallucinated_claim | db_check_blindspot",
  "evidence_indices": [3, 7],
  "rationale": "concise evidence-backed explanation citing [msg_index] and privileged ground truth"
}"""


def _load_p1_driver():
    spec = importlib.util.spec_from_file_location("run_p1_taubench", root / "scripts/run_p1_taubench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def annotate_one(
    trace_id: str,
    messages: list[dict[str, Any]],
    privileged_context: Mapping[str, Any],
    client: LLMClient,
    *,
    tag: str,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    ledger = extract_evidence_ledger(messages)
    payload = {
        "privileged_ground_truth": privileged_context,
        "system_context": ledger["system_summary"],
        "user_requests": ledger["user_requests"],
        "tool_events": ledger["tool_events"],
        "assistant_turns": ledger["assistant_turns"],
    }
    prompt_msgs = [
        {"role": "system", "content": PRIVILEGED_ANNOTATOR_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)},
    ]
    try:
        res = client.complete(
            prompt_msgs,
            thinking=False,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            repeat_id="silver.0",
            tag=tag,
        )
        parsed = json.loads(res.text)
        label = parsed.get("silver_label")
        if label not in ("pass", "fail"):
            raise ValueError(f"invalid silver_label: {label!r}")
        return {
            "trace_id": trace_id,
            "provider": client.settings.provider,
            "model": client.settings.judge_model,
            "status": "ok",
            "silver_label": label,
            "primary_defect_type": str(parsed.get("primary_defect_type") or "none"),
            "evidence_indices": parsed.get("evidence_indices") or [],
            "rationale": str(parsed.get("rationale") or ""),
            "timestamp": utc_now(),
        }
    except LLMError as exc:
        return {"trace_id": trace_id, "status": "error", "reason": str(exc), "fatal": True}
    except Exception as exc:
        return {"trace_id": trace_id, "status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("taubench_blindspots", "claw48"))
    parser.add_argument("--provider", required=True, help="Cross-vendor provider (must NOT be deepseek/deepseek_pro)")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--cap-usd", type=float)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=2048)
    args = parser.parse_args(argv)

    if args.provider in ("deepseek", "deepseek_pro"):
        parser.error("P1-3 anti-circularity rule: privileged AI annotator MUST use a non-DeepSeek vendor (e.g. qwen or glm)")

    drv = _load_p1_driver()
    settings = load_provider_settings(args.provider, require_key=args.run)
    price = load_pricing(settings.pricing_file).get(settings.judge_model)
    if price is None:
        raise ValueError(f"verify pricing for {settings.judge_model!r} in {settings.pricing_file} before running (D5)")

    if args.target == "taubench_blindspots":
        cohort = drv.load_cohort()
        items = [t for t in cohort if t["objective_pass"]][: args.limit]
        est_usd = len(items) * (5500 * price.input_per_mtok + 300 * price.output_per_mtok) / 1_000_000
        if not args.run:
            print(json.dumps({"target": args.target, "provider": args.provider, "n_pass_traces": len(items), "est_peak_usd": round(est_usd, 4)}, indent=2))
            return 0
        if not args.cap_usd or not math.isfinite(args.cap_usd) or args.cap_usd <= 0:
            parser.error("--run requires positive --cap-usd")
        run_dir = root / "runs" / f"p13-silver-{args.provider}-blindspots"
        run_settings = drv._apply_budget_guard(settings, run_dir, args.cap_usd)
        client = LLMClient(run_settings, max_attempts=2, timeout=120.0)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(
                lambda t: annotate_one(t["trace_id"], t["messages"], t["privileged_outcome"], client, tag=f"p13/{t['trace_id']}", max_tokens=args.max_tokens),
                items,
            ))
        out_jsonl = OUT_DIR / f"silver_{args.provider}_taubench_passes.jsonl"
        atomic_text(out_jsonl, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        flagged = [r for r in rows if r.get("status") == "ok" and r.get("silver_label") == "fail"]
        md_lines = ["# τ-bench Objective-Pass Blind-Spot Audit (Silver Label vs DB Reward=1.0)\n"]
        for r in flagged[:20]:
            md_lines.append(f"- **{r['trace_id']}** (`{r['primary_defect_type']}`, indices={r['evidence_indices']}): {r['rationale']}")
        atomic_text(OUT_DIR / "taubench_blindspot_audit.md", "\n".join(md_lines) + "\n")
        summary = {
            "generated_at": utc_now(),
            "provider": args.provider,
            "model": settings.judge_model,
            "label_role": "silver_label_only",
            "n_audited_passes": sum(1 for r in rows if r.get("status") == "ok"),
            "n_errors": sum(1 for r in rows if r.get("status") != "ok"),
            "n_flagged_blindspots": len(flagged),
            "blindspot_rate": round(len(flagged) / max(1, sum(1 for r in rows if r.get("status") == "ok")), 4),
            "sample_for_human_review_count": min(20, len(flagged)),
        }
        atomic_text(root / "reports/p13_blindspot_summary.json", json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    # claw48 cross-check against human v2 labels
    spec = importlib.util.spec_from_file_location("run_stage3_and_neutral", root / "scripts/run_stage3_and_neutral.py")
    assert spec and spec.loader
    s3_drv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s3_drv)
    traces = s3_drv.load_frozen_traces(root)
    cohort_v2 = s3_drv.labeled_cohort(root, apply_amendments=True)
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text(encoding="utf-8"))
    official_by_tid = {c["trace_id"]: c for c in meta["chosen"]}

    if not args.run:
        est_usd = len(cohort_v2) * (6500 * price.input_per_mtok + 300 * price.output_per_mtok) / 1_000_000
        print(json.dumps({"target": "claw48", "provider": args.provider, "n_traces": len(cohort_v2), "est_peak_usd": round(est_usd, 4)}, indent=2))
        return 0
    if not args.cap_usd or not math.isfinite(args.cap_usd) or args.cap_usd <= 0:
        parser.error("--run requires positive --cap-usd")

    run_dir = root / "runs" / f"p13-silver-{args.provider}-claw48"
    run_settings = drv._apply_budget_guard(settings, run_dir, args.cap_usd)
    client = LLMClient(run_settings, max_attempts=2, timeout=120.0)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor

    def _run_claw_one(tid: str) -> dict[str, Any]:
        priv = {"claw_eval_official_passed": bool((official_by_tid.get(tid) or {}).get("passed")), "task_id": traces[tid]["task_id"]}
        row = annotate_one(tid, traces[tid]["messages"], priv, client, tag=f"p13-claw/{tid}", max_tokens=args.max_tokens)
        row["human_v2_pass"] = bool(cohort_v2[tid]["human_pass"])
        row["blind_id"] = cohort_v2[tid]["blind_id"]
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_run_claw_one, sorted(cohort_v2)))
    out_jsonl = OUT_DIR / f"silver_{args.provider}_claw48.jsonl"
    atomic_text(out_jsonl, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    h_vec = [bool(r["human_v2_pass"]) for r in ok_rows]
    s_vec = [r["silver_label"] == "pass" for r in ok_rows]
    disagree = [r for r in ok_rows if (r["silver_label"] == "pass") != bool(r["human_v2_pass"])]
    md_lines = ["# Claw-Eval 48 Human-v2 vs Privileged AI Silver Label Disagreements (for round3_adjudicated)\n"]
    for r in disagree:
        md_lines.append(
            f"- **{r['blind_id']}** (human_v2=`{'pass' if r['human_v2_pass'] else 'fail'}`, "
            f"silver=`{r['silver_label']}`, defect=`{r['primary_defect_type']}`, indices={r['evidence_indices']}): {r['rationale']}"
        )
    atomic_text(OUT_DIR / "claw48_disagreements.md", "\n".join(md_lines) + "\n")
    summary = {
        "generated_at": utc_now(),
        "provider": args.provider,
        "model": settings.judge_model,
        "label_role": "silver_label_only",
        "n_valid": len(ok_rows),
        "n_errors": sum(1 for r in rows if r.get("status") != "ok"),
        "raw_agreement_vs_human_v2": round(m.accuracy(h_vec, s_vec), 4) if ok_rows else None,
        "kappa_vs_human_v2": round(m.cohen_kappa(h_vec, s_vec), 4) if ok_rows and m.cohen_kappa(h_vec, s_vec) is not None else None,
        "pabak_vs_human_v2": round(m.pabak(h_vec, s_vec), 4) if ok_rows else None,
        "n_disagreements_for_adjudication": len(disagree),
    }
    atomic_text(root / "reports/p13_claw48_silver_agreement.json", json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
