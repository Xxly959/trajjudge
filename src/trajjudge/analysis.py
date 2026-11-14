"""Offline joins and paired analyses. Missing/error grades never become zero."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence

from . import metrics as m
from .agreement import THRESHOLDS


def agreement_with_clusters(rows: Sequence[Mapping[str, Any]], *, resamples: int = 2000,
                            policy: str = "v1", cluster_unit: str = "task_id",
                            scenarios: Mapping[str, str] | None = None) -> dict[str, Any]:
    """RQ1 agreement with cluster CIs, including category and baseline CIs.

    ``scenarios`` maps task_id to the independent scenario unit; without it the
    historical task_id clustering is used, which treats translation copies as
    independent and therefore understates interval width.
    """
    from .agreement import agreement_report, compare
    if policy not in ("v1", "v2"):
        raise ValueError(f"unknown ci policy {policy!r}")
    if not rows:
        raise ValueError("human labels required; no agreement result can be inferred")
    result = agreement_report(rows)
    unit = lambda r: (scenarios or {}).get(r["task_id"], r["task_id"])

    def interval(items: Sequence[Any], clusters: Sequence[str], stat: Callable[[Sequence[Any]], float | None]) -> dict[str, Any]:
        if policy == "v2":
            return cluster_interval(items, clusters, stat, resamples=resamples)
        return {"ci": cluster_ci(items, clusters, stat, resamples=resamples)}

    def intervals(items: Sequence[Any], pred: Callable[[Any], bool], entry: dict[str, Any]) -> None:
        clusters = [unit(r) for r in items]
        for name, func in (("accuracy", m.accuracy), ("kappa", m.cohen_kappa)):
            res = interval(items, clusters, lambda data, f=func: f(
                [r["human"] for r in data], [pred(r) for r in data]))
            entry[name + "_ci"] = res["ci"]
            if policy == "v2":
                entry[name + "_interval"] = res
        entry["bootstrap_clusters"] = len(set(clusters))
        entry["cluster_unit"] = cluster_unit
        entry["baseline_ci"] = {
            "always_pass": interval(items, clusters, lambda data: sum(r["human"] for r in data) / len(data))["ci"],
            "majority": interval(items, clusters, lambda data: max(sum(r["human"] for r in data), sum(not r["human"] for r in data)) / len(data))["ci"],
            "random_expected": (.5, .5)}
        entry["baselines"]["random"] = .5

    intervals(rows, lambda r: r["official"], result["official_vs_human"])
    result["bootstrap_clusters"] = len({unit(r) for r in rows})
    result["bootstrap_unit"] = f"{cluster_unit}; both agent configurations stay together"
    result["ci_policy"] = policy
    result["undefined_ci_policy"] = (
        "undefined draws counted; share >0.10 unreliable; fewer than two contributing clusters or zero width -> null"
        if policy == "v2" else
        "undefined bootstrap draws omitted; CI null when fewer than half are defined")
    for grader, entry in result["graders"].items():
        usable = [r for r in rows if r["scores"].get(grader) is not None]
        decision = lambda r, g=grader: r["scores"][g] >= THRESHOLDS[g]
        intervals(usable, decision, entry)
        auc_res = interval(usable, [unit(r) for r in usable], lambda data: m.auc(
            [r["human"] for r in data], [r["scores"][grader] for r in data]))
        entry["auc_ci"] = auc_res["ci"]
        if policy == "v2":
            entry["auc_interval"] = auc_res
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


def cluster_interval(items: Sequence[Any], clusters: Sequence[str], statistic: Callable[[Sequence[Any]], float | None],
                     *, resamples: int = 2000, seed: int = 0, contributing: int | None = None,
                     undefined_limit: float = 0.10) -> dict[str, Any]:
    """PREREG_v2 §2 interval: undefined draws accounted for, zero width refused.

    ``contributing`` is the number of clusters that can inform the statistic; it
    defaults to every cluster in the frame, which is right for agreement and
    stability but must be passed explicitly for a baseline-fail flip rate.
    """
    groups: dict[str, list[Any]] = defaultdict(list)
    for item, cluster in zip(items, clusters, strict=True):
        groups[cluster].append(item)
    values = list(groups.values())
    if not values:
        return {"ci": None, "resamples": resamples, "undefined_draws": 0, "undefined_share": 0.0,
                "defined_draws": 0, "clusters": 0, "contributing_clusters": 0,
                "status": "not_estimable", "reason": m.NOT_ESTIMABLE}
    return m.bootstrap_interval(lambda idx: statistic([item for i in idx for item in values[i]]), len(values),
                                resamples=resamples, seed=seed, undefined_limit=undefined_limit,
                                contributing_clusters=len(values) if contributing is None else contributing)


def stability_report(rows: Sequence[Mapping[str, Any]], *, repeats: int = 3, resamples: int = 2000,
                     task_ids: Mapping[str, str] | None = None, policy: str = "v1",
                     cluster_unit: str = "task_id") -> list[dict[str, Any]]:
    """Summarize complete repeat panels; report incomplete panels separately."""
    if policy not in ("v1", "v2"):
        raise ValueError(f"unknown ci policy {policy!r}")
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
                 "error_rows": sum(not _valid(r) for r in group), "summary": None, "ci": {},
                 "cluster_unit": cluster_unit}
        if complete:
            threshold = THRESHOLDS[group[0]["grader"]]
            summarize = lambda items: m.stability_summary({str(i): item[1] for i, item in enumerate(items)}, threshold)
            entry["summary"] = summarize(complete)
            clusters = [(task_ids or {}).get(tid, tid) for tid, _ in complete]
            for metric in ("mean_sd", "flip_rate", "pairwise_disagreement", "mean_spearman", "mean_kappa"):
                stat = lambda items, name=metric: summarize(items)[name]
                if policy == "v2":
                    interval = cluster_interval(complete, clusters, stat, resamples=resamples)
                    entry.setdefault("intervals", {})[metric] = interval
                    entry["ci"][metric] = interval["ci"]
                else:
                    entry["ci"][metric] = cluster_ci(complete, clusters, stat, resamples=resamples)
            entry["bootstrap_clusters"] = len(set(clusters))
        output.append(entry)
    return output


def injection_report(rows: Sequence[Mapping[str, Any]], *, resamples: int = 2000,
                     task_ids: Mapping[str, str] | None = None, policy: str = "v1",
                     cluster_unit: str = "task_id", case_study_scenarios: int = 5) -> list[dict[str, Any]]:
    """Pair variants with the same config/trace/repeat baseline, then aggregate by trace.

    ``policy="v2"`` applies PREREG_v2: the flip denominator is distinct baseline-fail
    trajectories, ASR and verdict flips are reported separately, undefined bootstrap
    draws are accounted for, and a flip rate over fewer than ``case_study_scenarios``
    independent scenarios is suppressed rather than stated as a percentage.
    """
    if policy not in ("v1", "v2"):
        raise ValueError(f"unknown ci policy {policy!r}")
    _check_unique(rows)
    originals = {(_group(r), r["trace_id"], r["repeat_id"]): r for r in rows if r.get("variant", "original") == "original"}
    groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for row in rows:
        if row.get("variant", "original") != "original":
            groups[(_group(row), row["variant"])].append(row)
    output = []
    for (config, variant), group in sorted(groups.items(), key=lambda item: str(item[0])):
        paired: dict[str, list[dict[str, Any]]] = defaultdict(list)
        missing = 0
        threshold = THRESHOLDS.get(group[0]["grader"])
        for r in group:
            base = originals.get((config, r["trace_id"], r["repeat_id"]))
            if base is None or not _valid(base) or not _valid(r):
                missing += 1
                continue
            base_fail = threshold is not None and base["score"] < threshold
            now_fail = threshold is not None and r["score"] < threshold
            paired[r["trace_id"]].append({
                "delta": r["score"] - base["score"],
                "base_fail": bool(base_fail),
                "fail_to_pass": bool(base_fail and not now_fail),
                "pass_to_fail": bool(threshold is not None and not base_fail and now_fail),
                "verdict_changed": bool(threshold is not None and base_fail != now_fail),
            })
        items = [{"trace_id": tid, "pairs": len(p),
                  "mean_delta": statistics.fmean(x["delta"] for x in p),
                  "positive": sum(x["delta"] > 0 for x in p),
                  "base_fail": sum(x["base_fail"] for x in p),
                  "fail_to_pass": sum(x["fail_to_pass"] for x in p),
                  "pass_to_fail": sum(x["pass_to_fail"] for x in p),
                  "verdict_changed": sum(x["verdict_changed"] for x in p)}
                 for tid, p in sorted(paired.items())]
        clusters = [(task_ids or {}).get(d["trace_id"], d["trace_id"]) for d in items]
        fail_items = [d for d in items if d["base_fail"]]
        fail_clusters = {c for d, c in zip(items, clusters, strict=True) if d["base_fail"]}
        n_pairs = sum(d["pairs"] for d in items)
        n_base_fail = sum(d["base_fail"] for d in items)

        def rate(numerator: str) -> Callable[[Sequence[Any]], float | None]:
            def stat(data: Sequence[Any]) -> float | None:
                denominator = sum(d["pairs"] for d in data)
                return sum(d[numerator] for d in data) / denominator if denominator else None
            return stat

        inflation = lambda data: statistics.fmean(d["mean_delta"] for d in data) if data else None
        flip = lambda data: (sum(d["fail_to_pass"] for d in data) / sum(d["base_fail"] for d in data)
                             if sum(d["base_fail"] for d in data) else None)
        asr, verdict_flip = rate("positive"), rate("verdict_changed")
        entry: dict[str, Any] = {
            "config": list(config), "variant": variant, "grader": group[0]["grader"],
            "paired_observations": n_pairs, "unpaired_observations": missing,
            "changed_observations": sum(x["delta"] != 0 for p in paired.values() for x in p),
            "traces": len(items), "bootstrap_clusters": len(set(clusters)), "cluster_unit": cluster_unit,
            "mean_inflation": inflation(items) if items else None,
            "baseline_fail_observations": n_base_fail,
            "fail_to_pass_observations": sum(d["fail_to_pass"] for d in items),
            "pass_to_fail_observations": sum(d["pass_to_fail"] for d in items),
            "verdict_changed_observations": sum(d["verdict_changed"] for d in items),
            "positive_observations": sum(d["positive"] for d in items),
            "asr": asr(items) if items else None,
            "verdict_flip_rate": verdict_flip(items) if items else None,
            "baseline_fail_traces": len(fail_items),
            "baseline_fail_scenarios": len(fail_clusters),
            "n_traj": len(fail_items), "n_scenario": len(fail_clusters), "pairs": n_base_fail,
            "case_study": len(fail_clusters) < case_study_scenarios,
        }
        if policy == "v1":
            entry["inflation_ci"] = cluster_ci(items, clusters, inflation, resamples=resamples)
            entry["baseline_fail_flip_rate"] = flip(items) if items else None
            entry["flip_ci"] = cluster_ci(items, clusters, flip, resamples=resamples)
            output.append(entry)
            continue

        entry["inflation_interval"] = cluster_interval(items, clusters, inflation, resamples=resamples)
        entry["asr_interval"] = cluster_interval(items, clusters, asr, resamples=resamples)
        entry["verdict_flip_interval"] = cluster_interval(items, clusters, verdict_flip, resamples=resamples)
        entry["flip_interval"] = cluster_interval(items, clusters, flip, resamples=resamples,
                                                  contributing=len(fail_clusters))
        entry["inflation_ci"] = entry["inflation_interval"]["ci"]
        entry["asr_ci"] = entry["asr_interval"]["ci"]
        entry["verdict_flip_ci"] = entry["verdict_flip_interval"]["ci"]
        entry["flip_ci"] = entry["flip_interval"]["ci"]
        if entry["case_study"]:
            entry["baseline_fail_flip_rate"] = None
            entry["flip_ci"] = None
            entry["flip_interval"] = {**entry["flip_interval"], "ci": None, "status": "not_estimable",
                                      "reason": m.NOT_ESTIMABLE}
            entry["flip_conclusion"] = None
        else:
            entry["baseline_fail_flip_rate"] = flip(items) if items else None
            entry["flip_conclusion"] = entry["baseline_fail_flip_rate"]
        output.append(entry)
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
