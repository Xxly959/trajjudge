#!/usr/bin/env python
"""Human annotation reliability: test-retest agreement and Cohen kappa with scenario-cluster CIs.

Reads owner-entered labels only; it never generates, suggests or fills a label.
Until gate A is satisfied it prints the outstanding human actions and computes no
label-dependent statistic (PREREG_v2 §5b).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import metrics as m  # noqa: E402
from trajjudge.analysis import cluster_interval  # noqa: E402
from trajjudge.annotation import read_exclusions, read_labels  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402

KAPPA_STABLE = 0.60
MIN_SCENARIOS = 5
MIN_GAP_HOURS = 48
TRACE_SUFFIX = re.compile(r"_[0-9a-f]{8}\.jsonl$")


def task_of(item: Mapping[str, Any]) -> str:
    """task_id from the frozen evidence path, so the private strata file stays closed."""
    return TRACE_SUFFIX.sub("", Path(item["trace"]).name)


def scenario_index(set_path: Path, map_path: Path) -> dict[str, str]:
    """trace_id -> scenario_id via task_id; an incomplete map is an error, not a silent fallback."""
    with map_path.open(newline="", encoding="utf-8") as handle:
        scenarios = {r["task_id"]: r["scenario_id"] for r in csv.DictReader(handle)}
    out = {}
    for item in json.loads(set_path.read_text(encoding="utf-8")):
        task = task_of(item)
        if task not in scenarios:
            raise ValueError(f"scenario map missing task_id {task}")
        out[item["trace_id"]] = scenarios[task]
    return out


def blind_units(key_path: Path, scenarios: Mapping[str, str]) -> dict[str, str]:
    """round-1 blind_id -> scenario_id, using the private key only as an id lookup."""
    return {blind: scenarios[trace] for trace, blind in json.loads(key_path.read_text(encoding="utf-8")).items()}


def blind_tasks(set_path: Path, key_path: Path) -> dict[str, str]:
    """round-1 blind_id -> task_id, for the comparison-only task_id clustering."""
    tasks = {i["trace_id"]: task_of(i) for i in json.loads(set_path.read_text(encoding="utf-8"))}
    return {blind: tasks[trace] for trace, blind in json.loads(key_path.read_text(encoding="utf-8")).items()}


def pair_rounds(round1: Sequence[Mapping[str, str]], round2: Sequence[Mapping[str, str]],
                round2_key: Mapping[str, str], *, excluded: Sequence[tuple[str, str]] = ()) -> tuple[list[dict], list[dict]]:
    """Join round-2 ids back to round 1 through the private key; every unpaired item gets a reason."""
    retired = {(b, str(r)) for b, r in excluded}
    first = {r["blind_id"]: r for r in round1 if str(r.get("round", "1")) == "1"}
    second = {r["blind_id"]: r for r in round2}
    pairs: list[dict] = []
    unpaired: list[dict] = []
    for fresh, blind in sorted(round2_key.items()):
        a, b = first.get(blind), second.get(fresh)
        if a is None:
            reason = "round 1 row missing"
        elif (blind, "1") in retired:
            reason = "round 1 excluded"
        elif not a["label"]:
            reason = "round 1 blank"
        elif b is None:
            reason = "round 2 row missing"
        elif (fresh, "2") in retired:
            reason = "round 2 excluded"
        elif not b["label"]:
            reason = "round 2 blank"
        else:
            pairs.append({"round1_blind_id": blind, "round2_blind_id": fresh,
                          "round1": a["label"], "round2": b["label"]})
            continue
        unpaired.append({"round1_blind_id": blind, "round2_blind_id": fresh, "reason": reason})
    selected = set(round2_key.values())
    unpaired += [{"round1_blind_id": blind, "round2_blind_id": None, "reason": "not selected for round 2"}
                 for blind in sorted(first) if blind not in selected]
    return pairs, unpaired


def _intervals(pairs: Sequence[Mapping[str, str]], units: Sequence[str], unit_name: str, *,
               resamples: int, seed: int) -> dict[str, Any]:
    a = lambda d: [x["round1"] == "pass" for x in d]
    b = lambda d: [x["round2"] == "pass" for x in d]
    return {
        "cluster_unit": unit_name,
        "clusters": len(set(units)),
        "raw_agreement": cluster_interval(pairs, units, lambda d: m.accuracy(a(d), b(d)), resamples=resamples, seed=seed),
        "kappa": cluster_interval(pairs, units, lambda d: m.cohen_kappa(a(d), b(d)), resamples=resamples, seed=seed),
    }


def agreement_stats(pairs: Sequence[Mapping[str, str]], units: Mapping[str, str], *,
                    task_units: Mapping[str, str] | None = None, resamples: int = 2000, seed: int = 0) -> dict[str, Any]:
    """Raw agreement, Cohen kappa and PABAK; scenario clusters are the primary unit."""
    a = [p["round1"] == "pass" for p in pairs]
    b = [p["round2"] == "pass" for p in pairs]
    clusters = [units[p["round1_blind_id"]] for p in pairs]
    n = len(pairs)
    transitions = Counter((p["round1"], p["round2"]) for p in pairs)
    out: dict[str, Any] = {
        "n_paired": n,
        "n_scenario_paired": len(set(clusters)),
        "labels_round1": m.label_counts(a),
        "labels_round2": m.label_counts(b),
        "transitions": {f"{x}_to_{y}": transitions[(x, y)] for x in ("pass", "fail") for y in ("pass", "fail")},
        "changed": sum(v for (x, y), v in transitions.items() if x != y),
        "case_study": len(set(clusters)) < MIN_SCENARIOS,
        "raw_agreement": m.accuracy(a, b) if n else None,
        "kappa": m.cohen_kappa(a, b) if n else None,
        "pabak": m.pabak(a, b) if n else None,
    }
    if n:
        out["intervals"] = _intervals(pairs, clusters, "scenario_id", resamples=resamples, seed=seed)
        if task_units is not None:
            out["task_id_intervals"] = _intervals(pairs, [task_units[p["round1_blind_id"]] for p in pairs],
                                                  "task_id", resamples=resamples, seed=seed)
    return out


def stability_verdict(stats: Mapping[str, Any]) -> dict[str, Any]:
    """PREREG_v2 §5b: human kappa below 0.60 means the gold standard itself is unstable."""
    if not stats.get("n_paired"):
        return {"status": "blocked", "gold_standard_unstable": None,
                "statement": "闸门 A 未通过：没有配对标签，不做任何依赖标签的分析"}
    interval = stats.get("intervals", {}).get("kappa", {})
    kappa = stats.get("kappa")
    if kappa is None or interval.get("ci") is None:
        return {"status": "not_estimable", "gold_standard_unstable": None,
                "statement": "无法判定金标准稳定性（κ 区间不可估）", "reason": interval.get("reason")}
    if kappa < KAPPA_STABLE:
        return {"status": "unstable", "gold_standard_unstable": True,
                "statement": f"人类 test-retest κ={kappa:.4f} < {KAPPA_STABLE}：金标准不稳定，"
                             "评分器与人类的一致度指标降级为 exploratory"}
    low = interval["ci"][0]
    if low < KAPPA_STABLE:
        return {"status": "unconfirmed", "gold_standard_unstable": False,
                "statement": f"κ={kappa:.4f} ≥ {KAPPA_STABLE}，但 CI 下界 {low:.4f} < {KAPPA_STABLE}：稳定性未确证"}
    return {"status": "stable", "gold_standard_unstable": False,
            "statement": f"κ={kappa:.4f}，CI 下界 {low:.4f} ≥ {KAPPA_STABLE}：金标准稳定性在本样本上成立"}


def grader_comparison(report_path: Path, human: Mapping[str, Any], verdict: Mapping[str, Any]) -> dict[str, Any]:
    """Grader-vs-human kappa next to human-vs-self kappa; reporting only the former is not allowed."""
    if not report_path.is_file():
        return {"available": False, "reason": f"{report_path} not found"}
    agreement = json.loads(report_path.read_text(encoding="utf-8")).get("agreement", {})
    entries = dict(agreement.get("graders", {}))
    if "official_vs_human" in agreement:
        entries["framework_rubric"] = agreement["official_vs_human"]
    return {
        "available": True,
        "source": str(report_path),
        "human_test_retest_kappa": human.get("kappa"),
        "human_kappa_ci": human.get("intervals", {}).get("kappa", {}).get("ci"),
        "gold_standard_unstable": verdict.get("gold_standard_unstable"),
        "grader_metrics_downgraded": verdict.get("gold_standard_unstable") is True,
        "raters": {name: {"n": e.get("n"), "kappa": e.get("kappa"), "kappa_ci": e.get("kappa_ci"),
                          "accuracy": e.get("accuracy"), "auc": e.get("auc")}
                   for name, e in sorted(entries.items())},
    }


def gate_status(round1: Sequence[Mapping[str, str]], round2: Sequence[Mapping[str, str]],
                round2_key: Mapping[str, str], excluded: Mapping[tuple[str, str], Any], *,
                now: datetime | None = None) -> dict[str, Any]:
    """What the owner still has to do; the assistant may not do any of it."""
    first = [r for r in round1 if str(r.get("round", "1")) == "1"]
    blanks = [r["blind_id"] for r in first if not r["label"] and (r["blind_id"], "1") not in excluded]
    labeled = [r for r in first if r["label"]]
    round2_blanks = [r["blind_id"] for r in round2
                     if not r["label"] and (r["blind_id"], "2") not in excluded]
    now = now or datetime.now(timezone.utc)
    hours = None
    if labeled:
        last = max(datetime.fromisoformat(r["annotated_at"]) for r in labeled)
        hours = round((now - last).total_seconds() / 3600, 1)
    actions = []
    if blanks:
        actions.append(f"round 1 还有 {len(blanks)} 条空白 {blanks}：给标签，或 "
                       "`python scripts/annotate.py exclude --blind-id <id> --reason <原因>` 显式退役")
    if not round2_key:
        actions.append("运行 `python scripts/annotate.py round2` 构建第二轮盲标 kit（助手可代跑，标签仍由你给）")
    elif round2_blanks:
        actions.append(f"完成第二轮 {len(round2_blanks)} 条："
                       "`python scripts/annotate.py label --round 2 --csv annotation/round2_labels.csv`")
    if hours is not None and hours < MIN_GAP_HOURS:
        actions.append(f"距第一轮最后一条标签仅 {hours:.1f}h，需 ≥ {MIN_GAP_HOURS}h")
    ready = not blanks and bool(round2_key) and not round2_blanks and (hours is None or hours >= MIN_GAP_HOURS)
    return {
        "ready": ready,
        "round1": {"rows": len(first), "labeled": len(labeled), "blank": len(blanks),
                   "blank_ids": blanks, "excluded": sum(1 for _, r in excluded if r == "1")},
        "round2": {"selected": len(round2_key), "rows": len(round2),
                   "labeled": sum(bool(r["label"]) for r in round2), "blank": len(round2_blanks),
                   "blank_ids": round2_blanks},
        "hours_since_round1": hours,
        "min_gap_hours": MIN_GAP_HOURS,
        "actions": actions,
    }


def second_annotator(rows: Sequence[Mapping[str, str]], round1: Sequence[Mapping[str, str]],
                     units: Mapping[str, str], *, resamples: int, seed: int) -> dict[str, Any]:
    """Inter-annotator agreement on shared blind ids; test-retest must never stand in for it."""
    first = {r["blind_id"]: r["label"] for r in round1 if str(r.get("round", "1")) == "1" and r["label"]}
    pairs = [{"round1_blind_id": r["blind_id"], "round2_blind_id": r["blind_id"],
              "round1": first[r["blind_id"]], "round2": r["label"]}
             for r in rows if r["label"] and r["blind_id"] in first]
    if not pairs:
        return {"available": False, "n_paired": 0,
                "statement": "第二标注者没有与第一轮重叠的已标注项，无法计算 inter-annotator κ"}
    stats = agreement_stats(pairs, units, resamples=resamples, seed=seed)
    stats["available"] = True
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round1", type=Path, default=root / "annotation/labels.csv")
    parser.add_argument("--round2", type=Path, default=root / "annotation/round2_labels.csv")
    parser.add_argument("--round2-key", type=Path, default=root / "outputs/annotation/round2_key.json")
    parser.add_argument("--key", type=Path, default=root / "outputs/annotation/key.json")
    parser.add_argument("--set", type=Path, default=root / "outputs/p2/annotation_set.json")
    parser.add_argument("--scenario-map", type=Path, default=root / "reports/scenario_map.csv")
    parser.add_argument("--exclusions", type=Path, default=root / "annotation/exclusions.jsonl")
    parser.add_argument("--second", type=Path, help="optional second-annotator CSV on the same round-1 blind ids")
    parser.add_argument("--grader-report", type=Path, default=root / "reports/p2-v2.json")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=root / "reports/annotator_agreement.json")
    args = parser.parse_args()

    round1 = read_labels(args.round1)
    round2 = read_labels(args.round2) if args.round2.is_file() else []
    round2_key = json.loads(args.round2_key.read_text(encoding="utf-8")) if args.round2_key.is_file() else {}
    excluded = read_exclusions(args.exclusions)
    gate = gate_status(round1, round2, round2_key, excluded)
    scenarios = scenario_index(args.set, args.scenario_map)
    units = blind_units(args.key, scenarios)
    tasks = blind_tasks(args.set, args.key)
    result: dict[str, Any] = {"status": "blocked" if not gate["ready"] else "ok", "gate": gate,
                              "prereg": "docs/PREREG_v2.md §5b", "kappa_stability_threshold": KAPPA_STABLE,
                              "resamples": args.resamples, "seed": args.seed,
                              "second_annotator": {"available": False,
                                                   "statement": "单标注者，无 inter-annotator 一致度"}}
    pairs, unpaired = pair_rounds(round1, round2, round2_key, excluded=sorted(excluded))
    result["unpaired"] = unpaired
    result["coverage"] = {"n_paired": len(pairs), "n_round2_selected": len(round2_key),
                          "n_unpaired": len(unpaired)}
    if args.second is not None and args.second.is_file():
        result["second_annotator"] = second_annotator(read_labels(args.second), round1, units,
                                                      resamples=args.resamples, seed=args.seed)
    if not gate["ready"] or not pairs:
        result["test_retest"] = None
        result["verdict"] = stability_verdict({"n_paired": 0})
        print("闸门 A 未通过：不计算任何依赖标签的一致度指标。")
        for action in gate["actions"] or ["完成第二轮标注"]:
            print(f"  - {action}")
        print(f"round 1: {gate['round1']['labeled']}/{gate['round1']['rows']} 已标注，"
              f"{gate['round1']['excluded']} 显式排除；round 2: {gate['round2']['labeled']}/{gate['round2']['selected']}")
    else:
        stats = agreement_stats(pairs, units, task_units=tasks, resamples=args.resamples, seed=args.seed)
        verdict = stability_verdict(stats)
        result["test_retest"] = stats
        disputed = {"B78c979", "Bed2fd2"}
        trimmed_pairs = [p for p in pairs if p["round1_blind_id"] not in disputed]
        if trimmed_pairs and len(trimmed_pairs) < len(pairs):
            result["test_retest_excluding_disputed"] = {
                "excluded_blind_ids": sorted(disputed & {p["round1_blind_id"] for p in pairs}),
                "n_round2_selected": len(round2_key) - (len(pairs) - len(trimmed_pairs)),
                **agreement_stats(trimmed_pairs, units, task_units=tasks, resamples=args.resamples, seed=args.seed),
            }
        result["verdict"] = verdict
        result["grader_comparison"] = grader_comparison(args.grader_report, stats, verdict)
        print(f"配对 {stats['n_paired']} 条轨迹 / {stats['n_scenario_paired']} 个独立场景"
              f"（第二轮抽中 {len(round2_key)}，未配对 {len(unpaired)}）")
        if stats["case_study"]:
            print(f"case study（独立场景 {stats['n_scenario_paired']} < {MIN_SCENARIOS}）："
                  f"两轮一致 {stats['n_paired'] - stats['changed']}/{stats['n_paired']}，不输出百分比结论句")
        else:
            print(f"原始一致度 {stats['raw_agreement']:.4f}，Cohen κ {stats['kappa']:.4f}，PABAK {stats['pabak']:.4f}")
        for name in ("raw_agreement", "kappa"):
            interval = stats["intervals"][name]
            print(f"  {name} 区间: {interval['ci']} status={interval['status']} "
                  f"undefined={interval['undefined_draws']}/{interval['resamples']}")
        print(f"判定: {verdict['statement']}")
        print(f"第二标注者: {result['second_annotator']['statement']}")
    atomic_text(args.output, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(f"written: {args.output.relative_to(root) if args.output.is_relative_to(root) else args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())