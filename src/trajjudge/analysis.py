"""Offline joins and paired analyses. Missing/error grades never become zero."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence

from . import metrics as m
from .agreement import THRESHOLDS


def agreement_with_clusters(rows: Sequence[Mapping[str, Any]], *, resamples: int = 2000) -> dict[str, Any]:
    """RQ1 agreement with task-cluster CIs, including category and baseline CIs."""
    from .agreement import agreement_report, compare
    if not rows:
        raise ValueError("human labels required; no agreement result can be inferred")
    result = agreement_report(rows)

    def intervals(items: Sequence[Any], pred: Callable[[Any], bool], entry: dict[str, Any]) -> None:
        clusters = [r["task_id"] for r in items]
        for name, func in (("accuracy", m.accuracy), ("kappa", m.cohen_kappa)):
            entry[name + "_ci"] = cluster_ci(items, clusters, lambda data, f=func: f(
                [r["human"] for r in data], [pred(r) for r in data]), resamples=resamples)
        entry["bootstrap_clusters"] = len(set(clusters))
        entry["baseline_ci"] = {
            "always_pass": cluster_ci(items, clusters, lambda data: sum(r["human"] for r in data) / len(data), resamples=resamples),
            "majority": cluster_ci(items, clusters, lambda data: max(sum(r["human"] for r in data), sum(not r["human"] for r in data)) / len(data), resamples=resamples),
            "random_expected": (.5, .5)}
        entry["baselines"]["random"] = .5

    intervals(rows, lambda r: r["official"], result["official_vs_human"])
    result["bootstrap_clusters"] = len({r["task_id"] for r in rows})
    result["bootstrap_unit"] = "task; both agent configurations stay together"
    result["undefined_ci_policy"] = "undefined bootstrap draws omitted; CI null when fewer than half are defined"
    for grader, entry in result["graders"].items():
        usable = [r for r in rows if r["scores"].get(grader) is not None]
        decision = lambda r, g=grader: r["scores"][g] >= THRESHOLDS[g]
        intervals(usable, decision, entry)
        entry["auc_ci"] = cluster_ci(usable, [r["task_id"] for r in usable], lambda data: m.auc(
            [r["human"] for r in data], [r["scores"][grader] for r in data]), resamples=resamples)
        official_items = [{**r, "human": r["official"]} for r in usable]
        intervals(official_items, decision, entry["vs_official"])
        for category in entry["per_category"]:
            subset = [r for r in usable if r["category"] == category]
            cat = compare([r["human"] for r in subset], [decision(r) for r in subset])
            intervals(subset, decision, cat)
            entry["per_category"][category] = cat
    return result


def _valid(row: Mapping[str, Any]) -> bool:
    score = row.get("score")
    return row.get("status") == "ok" and type(score) in (int, float) and math.isfinite(score)


def _group(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (row["config"], row.get("judge_model"), row.get("max_tokens"), row.get("openjudge_commit"))


def _check_unique(rows: Sequence[Mapping[str, Any]]) -> None:
    keys = [(_group(r), r["trace_id"], r.get("variant", "original"), r["repeat_id"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate analysis rows; select latest explicit retry before analysis")


def cluster_ci(items: Sequence[Any], clusters: Sequence[str], statistic: Callable[[Sequence[Any]], float | None],
               *, resamples: int = 2000, seed: int = 0) -> tuple[float, float] | None:
    """Bootstrap independent task clusters, keeping all within-task records together."""
    groups: dict[str, list[Any]] = defaultdict(list)
    for item, cluster in zip(items, clusters, strict=True):
        groups[cluster].append(item)
    values = list(groups.values())
    if not values:
        return None
    return m.bootstrap_ci(lambda idx: statistic([item for i in idx for item in values[i]]), len(values),
                          resamples=resamples, seed=seed)


def stability_report(rows: Sequence[Mapping[str, Any]], *, repeats: int = 3, resamples: int = 2000,
                     task_ids: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Summarize complete repeat panels; report incomplete panels separately."""
    if repeats < 3:
        raise ValueError("formal stability analysis needs at least three repeats")
    if any(type(r["repeat_id"]) is not int or r["repeat_id"] not in range(repeats) for r in rows):
        raise ValueError("observed repeat ids conflict with expected repeat panel; do not truncate")
    _check_unique(rows)
    groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for row in rows:
        if row.get("variant", "original") == "original":
            groups[_group(row)].append(row)
    output = []
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        panel: dict[str, dict[int, float]] = defaultdict(dict)
        all_ids = {r["trace_id"] for r in group}
        for r in group:
            if _valid(r):
                panel[r["trace_id"]][r["repeat_id"]] = r["score"]
        complete = [(tid, [values[i] for i in range(repeats)]) for tid, values in sorted(panel.items())
                    if all(i in values for i in range(repeats))]
        entry = {"config": list(key), "grader": group[0]["grader"], "expected_repeats": repeats,
                 "complete_traces": len(complete), "incomplete_traces": len(all_ids) - len(complete),
                 "error_rows": sum(not _valid(r) for r in group), "summary": None, "ci": {}}
        if complete:
            threshold = THRESHOLDS[group[0]["grader"]]
            summarize = lambda items: m.stability_summary({str(i): item[1] for i, item in enumerate(items)}, threshold)
            entry["summary"] = summarize(complete)
            clusters = [(task_ids or {}).get(tid, tid) for tid, _ in complete]
            for metric in ("mean_sd", "flip_rate", "pairwise_disagreement", "mean_spearman", "mean_kappa"):
                entry["ci"][metric] = cluster_ci(complete, clusters, lambda items, name=metric: summarize(items)[name], resamples=resamples)
            entry["bootstrap_clusters"] = len(set(clusters))
        output.append(entry)
    return output


def injection_report(rows: Sequence[Mapping[str, Any]], *, resamples: int = 2000,
                     task_ids: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Pair variants with the same config/trace/repeat baseline, then aggregate by trace."""
    _check_unique(rows)
    originals = {(_group(r), r["trace_id"], r["repeat_id"]): r for r in rows if r.get("variant", "original") == "original"}
    groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for row in rows:
        if row.get("variant", "original") != "original":
            groups[(_group(row), row["variant"])].append(row)
    output = []
    for (config, variant), group in sorted(groups.items(), key=lambda item: str(item[0])):
        paired: dict[str, list[Any]] = defaultdict(list)
        missing = 0
        threshold = THRESHOLDS.get(group[0]["grader"])
        for r in group:
            base = originals.get((config, r["trace_id"], r["repeat_id"]))
            if base is None or not _valid(base) or not _valid(r):
                missing += 1
                continue
            base_fail = threshold is not None and base["score"] < threshold
            flipped = base_fail and r["score"] >= threshold
            paired[r["trace_id"]].append((r["score"] - base["score"], base_fail, flipped))
        items = [(tid, statistics.fmean(p[0] for p in pairs),
                  sum(p[1] for p in pairs), sum(p[2] for p in pairs)) for tid, pairs in sorted(paired.items())]
        inflation = lambda data: statistics.fmean(p[1] for p in data)
        flip = lambda data: sum(p[3] for p in data) / sum(p[2] for p in data) if sum(p[2] for p in data) else None
        clusters = [(task_ids or {}).get(p[0], p[0]) for p in items]
        output.append({"config": list(config), "variant": variant, "grader": group[0]["grader"],
                       "paired_observations": sum(map(len, paired.values())), "unpaired_observations": missing,
                       "changed_observations": sum(p[0] != 0 for pairs in paired.values() for p in pairs),
                       "traces": len(items), "bootstrap_clusters": len(set(clusters)),
                       "mean_inflation": inflation(items) if items else None,
                       "inflation_ci": cluster_ci(items, clusters, inflation, resamples=resamples),
                       "baseline_fail_observations": sum(p[2] for p in items),
                       "fail_to_pass_observations": sum(p[3] for p in items),
                       "baseline_fail_flip_rate": flip(items) if items else None,
                       "flip_ci": cluster_ci(items, clusters, flip, resamples=resamples)})
    return output


def join_labels(candidates: Sequence[Mapping[str, Any]], key: Mapping[str, str], labels: Sequence[Mapping[str, str]],
                grades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Join first-round owner labels to fixed Direct/off/repeat-0 judge rows."""
    from .annotation import validate_labels
    first = [r for r in labels if r.get("round", "1") == "1"]
    problems = validate_labels(first, list(key.values()))
    if problems:
        raise ValueError("invalid owner labels: " + "; ".join(problems))
    human = {r["blind_id"]: r["label"] == "pass" for r in first if r["label"]}
    selected = [r for r in grades if r.get("thinking") is False and r.get("strategy", "direct") == "direct"
                and r.get("repeat_id") == 0 and r.get("variant", "original") == "original" and not r.get("defended", False)]
    _check_unique(selected)
    scores: dict[str, dict[str, float]] = defaultdict(dict)
    for grader in THRESHOLDS:
        group = [r for r in selected if r["grader"] == grader]
        if len({_group(r) for r in group}) > 1:
            raise ValueError("mixed judge configurations in RQ1")
        for r in group:
            if _valid(r):
                scores[r["trace_id"]][grader] = r["score"]
    joined = []
    for item in candidates:
        tid = item["trace_id"]
        if key.get(tid) not in human:
            continue
        joined.append({"trace_id": tid, "task_id": item["task_id"], "human": human[key[tid]],
                       "official": item["passed"], "category": item["category"], "scores": scores[tid]})
    return {"rows": joined, "labeled": len(joined), "selected": len(candidates),
            "missing_scores": {g: sum(g not in r["scores"] for r in joined) for g in THRESHOLDS}}
