#!/usr/bin/env python
"""Operating-point (threshold) scan & main-to-validation transfer analysis (Module B4)."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_run_rows(run_dir: Path) -> dict[str, dict[str, Any]]:
    rows_dir = run_dir / "rows"
    if not rows_dir.is_dir():
        raise FileNotFoundError(f"missing run rows dir: {rows_dir}")
    out: dict[str, dict[str, Any]] = {}
    for rf in sorted(rows_dir.glob("*.json")):
        row = json.loads(rf.read_text(encoding="utf-8"))
        tid = row.get("trace_id")
        if tid:
            prev = out.get(tid)
            if prev is None or str(row.get("timestamp", "")) >= str(prev.get("timestamp", "")):
                out[tid] = row
    return out


def extract_scores(
    cohort_traces: Sequence[Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    *,
    itt: bool = False,
) -> list[tuple[float, bool]]:
    """Return list of ``(score, objective_pass)`` pairs. In ITT mode, invalid/missing -> score=0.0."""
    out: list[tuple[float, bool]] = []
    for tr in sorted(cohort_traces, key=lambda x: str(x["trace_id"])):
        tid = str(tr["trace_id"])
        row = rows.get(tid)
        valid = (
            row is not None
            and row.get("status") == "ok"
            and type(row.get("score")) in (int, float)
            and math.isfinite(float(row["score"]))
        )
        if valid:
            out.append((float(row["score"]), bool(tr["objective_pass"])))  # type: ignore[index]
        elif itt:
            out.append((0.0, bool(tr["objective_pass"])))
    return out


def eval_at_threshold(pairs: Sequence[tuple[float, bool]], thr: float) -> dict[str, Any]:
    """Predict failure iff ``score < thr``; positive class = objective failure (objective_pass=False)."""
    n_fail = sum(not y for _, y in pairs)
    n_pass = sum(y for _, y in pairs)
    tp = sum(1 for s, y in pairs if (not y) and s < thr)
    fp = sum(1 for s, y in pairs if y and s < thr)
    return {
        "threshold": round(thr, 6),
        "n_eval": len(pairs),
        "n_fail": n_fail,
        "n_pass": n_pass,
        "tp": tp,
        "fp": fp,
        "recall": round(tp / n_fail, 4) if n_fail else None,
        "fpr": round(fp / n_pass, 4) if n_pass else None,
    }


def scan_curve(pairs: Sequence[tuple[float, bool]]) -> list[dict[str, Any]]:
    """Scan all distinct midpoints + boundaries where ``score < thr`` transitions."""
    uniq = sorted({s for s, _ in pairs})
    if not uniq:
        return []
    candidates: list[float] = [round(uniq[0] - 0.01, 6)]
    for i in range(len(uniq) - 1):
        candidates.append(round((uniq[i] + uniq[i + 1]) / 2.0, 6))
    candidates.append(round(uniq[-1] + 0.01, 6))
    return [eval_at_threshold(pairs, t) for t in candidates]


def select_main_thresholds(pairs: Sequence[tuple[float, bool]], *, default_thr: float) -> dict[str, Any]:
    """Select strict (FPR <= 10%) and loose (Recall >= 80%) thresholds on main cohort."""
    curve = scan_curve(pairs)
    strict_cands = [p for p in curve if p["fpr"] is not None and p["fpr"] <= 0.10 + 1e-12]
    strict = max(strict_cands, key=lambda p: (p["recall"] or -1.0, -(p["fpr"] or 1.0), -p["threshold"])) if strict_cands else None

    loose_cands = [p for p in curve if p["recall"] is not None and p["recall"] >= 0.80 - 1e-12]
    loose = min(loose_cands, key=lambda p: (p["fpr"] if p["fpr"] is not None else 1.0, -(p["recall"] or -1.0), p["threshold"])) if loose_cands else None

    # Check if loose collapses to always-fail (fpr == 1.0)
    nondegenerate = [p for p in curve if (p["fpr"] or 0.0) < 1.0 - 1e-12]
    best_nondeg_high_recall = max(nondegenerate, key=lambda p: (p["recall"] or -1.0, -(p["fpr"] or 1.0))) if nondegenerate else None

    return {
        "default_threshold": default_thr,
        "default_point": eval_at_threshold(pairs, default_thr),
        "strict_fpr_le_10": {
            "achievable": strict is not None,
            "threshold": strict["threshold"] if strict else None,
            "main_point": strict,
        },
        "loose_recall_ge_80": {
            "achievable": loose is not None,
            "nondegenerate": bool(loose and (loose["fpr"] or 0.0) < 1.0 - 1e-12),
            "threshold": loose["threshold"] if loose else None,
            "main_point": loose,
            "best_nondegenerate_point": best_nondeg_high_recall,
        },
        "n_curve_points": len(curve),
        "curve": curve,
    }


def _evaluate_transfer(
    main_traces: Sequence[Mapping[str, Any]],
    val_traces: Sequence[Mapping[str, Any]] | None,
    main_run_dir: Path,
    val_run_dir: Path | None,
    *,
    default_thr: float,
) -> dict[str, Any]:
    main_rows = load_run_rows(main_run_dir)
    main_cc = extract_scores(main_traces, main_rows, itt=False)
    main_itt = extract_scores(main_traces, main_rows, itt=True)

    sel_cc = select_main_thresholds(main_cc, default_thr=default_thr)
    out: dict[str, Any] = {
        "default_threshold": default_thr,
        "main_complete_case": sel_cc,
        "main_itt_curve": scan_curve(main_itt),
    }
    if val_traces is None or val_run_dir is None or not val_run_dir.is_dir():
        return out

    val_rows = load_run_rows(val_run_dir)
    val_cc = extract_scores(val_traces, val_rows, itt=False)
    val_itt = extract_scores(val_traces, val_rows, itt=True)

    frozen_tiers = {
        "default": default_thr,
        "strict_fpr_le_10": sel_cc["strict_fpr_le_10"]["threshold"],
        "loose_recall_ge_80": sel_cc["loose_recall_ge_80"]["threshold"],
    }
    # Add best nondegenerate high-recall tier if loose collapsed (e.g. Accuracy < 3.0)
    if not sel_cc["loose_recall_ge_80"]["nondegenerate"] and sel_cc["loose_recall_ge_80"]["best_nondegenerate_point"]:
        frozen_tiers["best_nondegenerate_high_recall"] = sel_cc["loose_recall_ge_80"]["best_nondegenerate_point"]["threshold"]

    transfer: dict[str, Any] = {}
    for tier, thr in frozen_tiers.items():
        if thr is None:
            continue
        m_cc = eval_at_threshold(main_cc, thr)
        v_cc = eval_at_threshold(val_cc, thr)
        m_itt = eval_at_threshold(main_itt, thr)
        v_itt = eval_at_threshold(val_itt, thr)
        transfer[tier] = {
            "frozen_threshold": thr,
            "main_complete_case": m_cc,
            "val_complete_case": v_cc,
            "drift_cc_pp": {
                "recall_pp": round(((v_cc["recall"] or 0.0) - (m_cc["recall"] or 0.0)) * 100.0, 2),
                "fpr_pp": round(((v_cc["fpr"] or 0.0) - (m_cc["fpr"] or 0.0)) * 100.0, 2),
            },
            "main_itt": m_itt,
            "val_itt": v_itt,
            "drift_itt_pp": {
                "recall_pp": round(((v_itt["recall"] or 0.0) - (m_itt["recall"] or 0.0)) * 100.0, 2),
                "fpr_pp": round(((v_itt["fpr"] or 0.0) - (m_itt["fpr"] or 0.0)) * 100.0, 2),
            },
        }
    out["transfer"] = transfer
    out["val_complete_case_curve"] = scan_curve(val_cc)
    out["val_itt_curve"] = scan_curve(val_itt)
    return out


def build_operating_points_report(*, main_only: bool = False) -> dict[str, Any]:
    main_cohort = json.loads((root / "outputs/p1/taubench_cohort.json").read_text(encoding="utf-8"))["traces"]
    val_path = root / "outputs/p1_val/taubench_val_v3.json"
    val_traces = None
    if not main_only and val_path.is_file():
        val_traces = json.loads(val_path.read_text(encoding="utf-8"))["traces"]

    specs = [
        ("evidence_grounded|glm-5.3-flash", "runs/p1-hubcore_glm_flash-evidence_grounded", "runs/p1val-hubcore_glm_flash-evidence_grounded", 0.50),
        ("trajectory_accuracy|glm-5.3-flash", "runs/p1-hubcore_glm_flash-accuracy", "runs/p1val-hubcore_glm_flash-accuracy", 2.00),
        ("trajectory_comprehensive|glm-5.3-flash", "runs/p1-hubcore_glm_flash-comprehensive", "runs/p1val-hubcore_glm_flash-comprehensive", 0.60),
    ]
    raters: dict[str, Any] = {}
    for key, main_rel, val_rel, def_thr in specs:
        val_dir = (root / val_rel) if val_traces is not None else None
        raters[key] = _evaluate_transfer(main_cohort, val_traces, root / main_rel, val_dir, default_thr=def_thr)

    report = {
        "generated_at": _utc_now(),
        "prediction_rule": "flag_fail iff score < threshold",
        "main_cohort_n": len(main_cohort),
        "validation_cohort_n": len(val_traces) if val_traces is not None else 0,
        "raters": raters,
    }
    if not main_only:
        atomic_text(root / "reports/operating_points_v3.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-only", action="store_true", help="Print main cohort frozen operating points without requiring validation run.")
    args = parser.parse_args(argv)
    rep = build_operating_points_report(main_only=args.main_only)
    compact = {}
    for k, v in rep["raters"].items():
        mc = v["main_complete_case"]
        compact[k] = {
            "default": mc["default_point"],
            "strict": {
                "thr": mc["strict_fpr_le_10"]["threshold"],
                "pt": mc["strict_fpr_le_10"]["main_point"],
            },
            "loose": {
                "thr": mc["loose_recall_ge_80"]["threshold"],
                "nondegenerate": mc["loose_recall_ge_80"]["nondegenerate"],
                "pt": mc["loose_recall_ge_80"]["main_point"],
                "best_nondeg": mc["loose_recall_ge_80"]["best_nondegenerate_point"],
            },
        }
        if "transfer" in v:
            compact[k]["transfer"] = {
                tier: {
                    "thr": td["frozen_threshold"],
                    "main_cc": (td["main_complete_case"]["recall"], td["main_complete_case"]["fpr"]),
                    "val_cc": (td["val_complete_case"]["recall"], td["val_complete_case"]["fpr"]),
                    "drift_cc_pp": td["drift_cc_pp"],
                    "val_itt": (td["val_itt"]["recall"], td["val_itt"]["fpr"]),
                }
                for tier, td in v["transfer"].items()
            }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
