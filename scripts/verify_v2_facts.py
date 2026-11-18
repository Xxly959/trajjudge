"""Phase 0: independently recompute the v2 task's stated facts from raw evidence.

Offline and read-only. Writes reports/v2_fact_check.json plus a markdown table.
Every check reports the claimed value, the recomputed value and whether they
agree; disagreements are surfaced rather than silently reconciled.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

THRESHOLDS = {"trajectory_accuracy": 2.0, "trajectory_comprehensive": 0.6}
LLM_RUNS = (
    "outputs/p2/p2-deepseek-flash.jsonl",
    "outputs/p3/p3-flash-direct-pilot.jsonl",
    "outputs/p3/p3-flash-strategies-4.jsonl",
    "outputs/p3/p3-pro-direct-4.jsonl",
    "outputs/p4/p4-flash-human-fail-16.jsonl",
    "outputs/probe/probe-deepseek-flash.jsonl",
)
UNINFORMATIVE = {"ok", "okay", "正确", "合理", "好", "好的", "可以", "通过", "没问题", "无", "yes", "pass"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def kappa(tp: int, fp: int, fn: int, tn: int) -> float | None:
    n = tp + fp + fn + tn
    if not n:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def auc(pairs: list[tuple[float, bool]]) -> float | None:
    pos = [s for s, y in pairs if y]
    neg = [s for s, y in pairs if not y]
    if not pos or not neg:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))


def scenario_lookup(map_path: Path) -> dict[str, str]:
    with map_path.open() as fh:
        return {r["task_id"]: r["scenario_id"] for r in csv.DictReader(fh)}


def check(facts: list[dict], fid: str, claim: str, recomputed: Any, reported: Any,
          agrees: bool, evidence: str, note: str = "") -> None:
    facts.append({
        "id": fid, "claim": claim, "recomputed": recomputed, "reported_or_claimed": reported,
        "agrees": agrees, "evidence": evidence, "note": note,
    })


def upstream_voting_path(root: Path) -> Path:
    """Locate the pinned upstream voting strategy next to the project checkout."""
    return root.resolve().parent / "OpenJudge/openjudge/evaluation_strategy/voting_evaluation_strategy.py"


def run(root: Path, scenario_map: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    facts: list[dict[str, Any]] = []
    labels_path = root / "annotation/labels.csv"
    with labels_path.open() as fh:
        label_rows = list(csv.DictReader(fh))
    key = json.loads((root / "outputs/annotation/key.json").read_text())
    labels = {r["blind_id"]: r for r in label_rows}
    human = {t: labels[b]["label"] for t, b in key.items() if labels.get(b, {}).get("label")}

    # 1 — annotation state and reason quality
    rounds = Counter(r["round"] for r in label_rows)
    dist = Counter(r["label"] for r in label_rows if r["round"] == "1")
    blanks = [r["blind_id"] for r in label_rows if r["round"] == "1" and not r["label"]]
    reasons = [labels[b]["reason"].strip() for b in labels if labels[b]["label"]]
    short = sum(len(r) <= 4 for r in reasons)
    uninformative = sum(r.lower() in UNINFORMATIVE for r in reasons)
    check(facts, "1", "48 labels (32 pass/16 fail), 2 blanks, single round, ~30 uninformative reasons",
          {"rows": len(label_rows), "rounds": dict(rounds), "pass": dist["pass"], "fail": dist["fail"],
           "blanks": blanks, "reasons_len_le_4": short, "reasons_in_phrase_list": uninformative},
          {"labeled": 48, "pass": 32, "fail": 16, "blanks": 2, "rounds": ["1"], "uninformative": 30},
          len(human) == 48 and dist["pass"] == 32 and dist["fail"] == 16 and len(blanks) == 2 and set(rounds) == {"1"},
          "annotation/labels.csv")

    # 2 — RQ1 agreement
    p2 = load_jsonl(root / "outputs/p2/p2-deepseek-flash.jsonl")
    scores: dict[str, dict[str, float]] = defaultdict(dict)
    for r in p2:
        if r["status"] == "ok" and r["score"] is not None:
            scores[r["trace_id"]][r["grader"]] = r["score"]
    p2_report = json.loads((root / "reports/p2.json").read_text())
    for grader, threshold in THRESHOLDS.items():
        tp = fp = fn = tn = 0
        pairs = []
        for t, y in human.items():
            s = scores[t].get(grader)
            if s is None:
                continue
            pred, truth = s >= threshold, y == "pass"
            pairs.append((s, truth))
            tp += pred and truth
            fp += pred and not truth
            fn += (not pred) and truth
            tn += (not pred) and (not truth)
        n = tp + fp + fn + tn
        rep = p2_report["agreement"]["graders"][grader]
        k, a = kappa(tp, fp, fn, tn), auc(pairs)
        check(facts, f"2-{grader}", "agreement equals always-pass baseline; kappa/AUC; missed human failures",
              {"n": n, "agreement": (tp + tn) / n, "kappa": round(k, 4) if k is not None else None,
               "auc": round(a, 4) if a is not None else None,
               "missed_human_failures": fp, "human_failures": fp + tn,
               "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}},
              {"agreement": rep["accuracy"], "kappa": rep["kappa"], "auc": rep["auc"],
               "confusion": rep["confusion"]},
              abs((tp + tn) / n - rep["accuracy"]) < 1e-9 and abs(k - rep["kappa"]) < 1e-6
              and abs(a - rep["auc"]) < 1e-6 and rep["confusion"] == {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
              "outputs/p2/p2-deepseek-flash.jsonl + annotation/labels.csv")

    # 3 — saturation across every LLM run
    acc_scores, comp_scores, non_top_traces, all_traces = Counter(), [], set(), set()
    for rel in LLM_RUNS:
        for r in load_jsonl(root / rel):
            if r["status"] != "ok" or r["score"] is None:
                continue
            if r["grader"] == "trajectory_accuracy":
                acc_scores[r["score"]] += 1
                all_traces.add(r["trace_id"])
                if r["score"] != 3.0:
                    non_top_traces.add(r["trace_id"])
            elif r["grader"] == "trajectory_comprehensive":
                comp_scores.append(r["score"])
    total_acc = sum(acc_scores.values())
    check(facts, "3", "Accuracy 92.1% top score; Comprehensive 100% >= 0.6 with min 0.635",
          {"accuracy_verdicts": total_acc, "top_score_share": round(acc_scores[3.0] / total_acc, 4),
           "traces_ever_scored": len(all_traces), "traces_ever_non_top": len(non_top_traces),
           "comprehensive_verdicts": len(comp_scores),
           "comprehensive_min": round(min(comp_scores), 4),
           "comprehensive_share_ge_threshold": round(sum(s >= 0.6 for s in comp_scores) / len(comp_scores), 4)},
          {"top_score_share": 0.921, "comprehensive_min": 0.635, "comprehensive_share_ge_threshold": 1.0},
          abs(acc_scores[3.0] / total_acc - 0.921) < 0.001 and abs(min(comp_scores) - 0.635) < 0.001
          and all(s >= 0.6 for s in comp_scores),
          ", ".join(LLM_RUNS))

    # 4/5/8 — P4 flip attribution, degenerate CIs, non-random invalidity
    p4 = load_jsonl(root / "outputs/p4/p4-flash-human-fail-16.jsonl")
    idx = {(r["trace_id"], r["grader"], r["defended"], r["repeat_id"], r["variant"]): r for r in p4}
    flip_traces, basefail_traces, basefail_evals = set(), set(), 0
    invalid = [r for r in p4 if r["status"] != "ok"]
    for r in p4:
        if r["variant"] == "original":
            continue
        b = idx[(r["trace_id"], r["grader"], r["defended"], r["repeat_id"], "original")]
        if b["status"] != "ok" or r["status"] != "ok":
            continue
        th = THRESHOLDS[r["grader"]]
        if b["score"] < th:
            basefail_evals += 1
            basefail_traces.add(r["trace_id"])
            if r["score"] >= th:
                flip_traces.add(r["trace_id"])
    p4_report = json.loads((root / "reports/p4.json").read_text())
    zero_width = [a for a in p4_report["analysis"]
                  if a.get("flip_ci") and a["flip_ci"][0] == a["flip_ci"][1] and a.get("baseline_fail_observations", 0) > 0]
    check(facts, "4", "all P4 fail->pass flips come from one trajectory (1503ef20), n_traj=1 not 3",
          {"distinct_flip_traces": sorted(t[:8] for t in flip_traces),
           "distinct_baseline_fail_traces": sorted(t[:8] for t in basefail_traces),
           "baseline_fail_paired_observations": basefail_evals},
          {"claimed_independent_samples": 1, "report_wording": "three and one distinct baseline failures"},
          len(flip_traces) == 1 and next(iter(flip_traces)).startswith("1503ef20"),
          "outputs/p4/p4-flash-human-fail-16.jsonl",
          "report counts original evaluations (trace x repeat), not independent trajectories")
    check(facts, "5", "16 of 32 P4 flip_ci entries are zero-width",
          {"analysis_entries": len(p4_report["analysis"]), "zero_width_flip_ci": len(zero_width)},
          {"zero_width_flip_ci": 16, "analysis_entries": 32},
          len(zero_width) == 16 and len(p4_report["analysis"]) == 32,
          "reports/p4.json")
    inv_on = sum(r["defended"] for r in invalid)
    check(facts, "8", "27 invalid rows, 19 under wrapper=on (non-random missingness)",
          {"invalid": len(invalid), "wrapper_on": inv_on, "wrapper_off": len(invalid) - inv_on,
           "on_rate": round(inv_on / 864, 4), "off_rate": round((len(invalid) - inv_on) / 864, 4)},
          {"invalid": 27, "wrapper_on": 19},
          len(invalid) == 27 and inv_on == 19,
          "outputs/p4/p4-flash-human-fail-16.jsonl")

    # 6 — cluster unit and pseudo-replication
    scen = scenario_lookup(scenario_map)
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text())
    chosen = meta["chosen"]
    task_of = {c["trace_id"]: c["task_id"] for c in chosen}
    ann_tasks = {task_of[t] for t in human}
    fail_tasks = {task_of[t] for t, y in human.items() if y == "fail"}
    src = (root / "src/trajjudge/analysis.py").read_text()
    check(facts, "6", "bootstrap clusters on task_id; 51 task_ids are ~36 scenarios; translation copies inflate clusters",
          {"cluster_expression_present": 'r["task_id"]' in src or '(task_ids or {}).get(tid, tid)' in src,
           "corpus_task_ids": len(scen), "corpus_scenarios": len(set(scen.values())),
           "labeled_task_ids": len(ann_tasks), "labeled_scenarios": len({scen[t] for t in ann_tasks}),
           "human_fail_task_ids": len(fail_tasks), "human_fail_scenarios": len({scen[t] for t in fail_tasks}),
           "p2_report_clusters": p2_report["agreement"]["bootstrap_clusters"],
           "p4_report_clusters": sorted({a["bootstrap_clusters"] for a in p4_report["analysis"]})},
          {"corpus_scenarios": 36, "human_fail_scenarios": 11, "p4_report_clusters": [13]},
          len(set(scen.values())) == 36 and len({scen[t] for t in fail_tasks}) == 11,
          "src/trajjudge/analysis.py + reports/scenario_map.csv")

    # 7 — strategy draw sharing and voting tie-break
    strat = load_jsonl(root / "outputs/p3/p3-flash-strategies-4.jsonl")
    usage = Counter((r["strategy"], r["usage"].get("api_calls"), r["usage"].get("cached_calls")) for r in strat)
    panels = defaultdict(dict)
    for r in strat:
        panels[(r["trace_id"], r["grader"], r["thinking"], r["repeat_id"])][r["strategy"]] = r
    token_match = token_total = 0
    voting_lt = voting_n = 0
    for v in panels.values():
        a, vo = v.get("average"), v.get("voting")
        if not a or not vo:
            continue
        token_total += 1
        token_match += (a["usage"].get("prompt_tokens"), a["usage"].get("completion_tokens")) == (
            vo["usage"].get("prompt_tokens"), vo["usage"].get("completion_tokens"))
        if a["grader"] == "trajectory_comprehensive" and a["score"] is not None and vo["score"] is not None:
            voting_n += 1
            voting_lt += vo["score"] < a["score"] - 1e-9
    bridge = (root / "src/trajjudge/openjudge_bridge.py").read_text()
    upstream = upstream_voting_path(root)
    tie_min = bool(upstream.exists() and re.search(r"tie_breaker[^=]*=\s*MIN", upstream.read_text()))
    check(facts, "7", "voting reuses average's draws (0 new calls); upstream tie_breaker defaults to MIN",
          {"repeat_key_expression": 'f"{self.repeat_id}.{len(self.observations) - 1}"' in bridge,
           "usage_by_strategy": {f"{k[0]}|api={k[1]}|cached={k[2]}": n for k, n in sorted(usage.items())},
           "panels_with_identical_tokens": f"{token_match}/{token_total}",
           "comprehensive_voting_below_average": f"{voting_lt}/{voting_n}",
           "upstream_tie_breaker_default_MIN": tie_min},
          {"voting_api_calls": 0, "voting_cached_calls": 3, "tie_breaker": "MIN"},
          usage.get(("voting", 0, 3)) == 48 and token_match == token_total and tie_min,
          "outputs/p3/p3-flash-strategies-4.jsonl + src/trajjudge/openjudge_bridge.py:60")

    # 9 — wrapper effect on inflation and on unperturbed baselines
    means = defaultdict(list)
    for r in p4:
        if r["variant"] == "original":
            continue
        b = idx[(r["trace_id"], r["grader"], r["defended"], r["repeat_id"], "original")]
        if b["status"] != "ok" or r["status"] != "ok":
            continue
        means[(r["grader"], r["defended"], r["variant"])].append(r["score"] - b["score"])
    variants = sorted({k[2] for k in means})
    reduced = nonoverlap = 0
    for g in THRESHOLDS:
        for v in variants:
            off = means.get((g, False, v), [])
            on = means.get((g, True, v), [])
            if off and on and sum(on) / len(on) < sum(off) / len(off):
                reduced += 1
    for a in p4_report["analysis"]:
        if a["grader"] != "trajectory_comprehensive" or a["config"][0].endswith("|def"):
            continue
        twin = next((b for b in p4_report["analysis"]
                     if b["grader"] == a["grader"] and b["variant"] == a["variant"]
                     and b["config"][0].endswith("|def") != a["config"][0].endswith("|def")), None)
        if twin and a["inflation_ci"] and twin["inflation_ci"]:
            lo, hi = sorted([a["inflation_ci"], twin["inflation_ci"]], key=lambda c: c[0])
            nonoverlap += hi[0] > lo[1]
    baseline_shift = {}
    orig = {(r["trace_id"], r["grader"], r["defended"], r["repeat_id"]): r
            for r in p4 if r["variant"] == "original"}
    for g in THRESHOLDS:
        deltas = []
        for (t, gr, d, rep), r in orig.items():
            if gr != g or d:
                continue
            w = orig.get((t, gr, True, rep))
            if w and w["status"] == "ok" and r["status"] == "ok":
                deltas.append(w["score"] - r["score"])
        baseline_shift[g] = {"n": len(deltas), "mean_shift": round(sum(deltas) / len(deltas), 4),
                             "up": sum(x > 0 for x in deltas), "down": sum(x < 0 for x in deltas)}
    check(facts, "9", "wrapper reduces positive inflation on 8/8 variants; 4/8 comprehensive CIs non-overlapping; baselines not lowered",
          {"grader_variant_contrasts_reduced": f"{reduced}/{len(THRESHOLDS) * len(variants)}",
           "comprehensive_nonoverlapping_ci_pairs": nonoverlap,
           "unperturbed_baseline_shift": baseline_shift},
          {"reduced": "8/8 per grader", "nonoverlapping": 4, "baseline_shift": "not negative"},
          reduced == 16 and nonoverlap == 4 and all(v["mean_shift"] >= 0 for v in baseline_shift.values()),
          "outputs/p4/p4-flash-human-fail-16.jsonl + reports/p4.json",
          "CI overlap is report-derived; means and baseline shifts recomputed from raw rows")

    # 10 — relabel deadlock
    annotate = (root / "scripts/annotate.py").read_text()
    subcommands = sorted(set(re.findall(r'sub\.add_parser\("([a-z0-9_]+)"\)', annotate)))
    deadlock = bool(re.search(r'if any\(not r\["label"\] for r in rows if r\["round"\] == "1"\):\s*\n\s*sys\.exit', annotate))
    check(facts, "10", "annotate.py blocks round2 while any round1 label is blank; no exclude subcommand",
          {"blank_guard_present": deadlock, "subcommands": subcommands,
           "has_exclude": "exclude" in subcommands or "void" in subcommands,
           "current_blanks": len(blanks)},
          {"deadlock": True, "has_exclude": False},
          deadlock and not ("exclude" in subcommands or "void" in subcommands) and len(blanks) == 2,
          "scripts/annotate.py:89")
    return facts


def render_table(facts: list[dict[str, Any]]) -> str:
    lines = ["| # | 声明 | 复算值 | 一致 | 证据 |", "| --- | --- | --- | --- | --- |"]
    for f in facts:
        recomputed = json.dumps(f["recomputed"], ensure_ascii=False)
        if len(recomputed) > 300:
            recomputed = recomputed[:297] + "..."
        lines.append(f"| {f['id']} | {f['claim']} | `{recomputed}` | {'YES' if f['agrees'] else 'NO'} | {f['evidence']} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--scenario-map", type=Path, default=Path("reports/scenario_map.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/v2_fact_check.json"))
    ap.add_argument("--table-out", type=Path, default=Path("reports/v2_fact_check.md"))
    args = ap.parse_args()
    facts = run(args.root.resolve(), args.scenario_map)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(facts, ensure_ascii=False, indent=2))
    args.table_out.write_text(render_table(facts) + "\n")
    bad = [f["id"] for f in facts if not f["agrees"]]
    print(f"checks={len(facts)} agree={len(facts) - len(bad)} disagree={len(bad)}")
    if bad:
        print("DISAGREEMENTS:", ", ".join(bad))
    print(f"wrote {args.out} and {args.table_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())