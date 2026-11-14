#!/usr/bin/env python
"""Phase 4: LOSO threshold calibration and the hard-sample failure taxonomy.

Zero API calls and zero new spend: labels are joined offline, thresholds are
calibrated leave-one-scenario-out, and the graders' raw output is recovered from
the disk cache under the same token+score identity check Phase 1 uses.

Everything here depends on round-1 human labels, so every output is PROVISIONAL
and exploratory (PREREG_v2 §7/§7b) and must not reach FINAL_REPORT_v2 or
RESUME_CLAIMS before gate A. Grader verbatim text is written only under reports/.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "scripts"))

from trajjudge import annotation as kit  # noqa: E402
from trajjudge import calibration as cal  # noqa: E402
from trajjudge import metrics as m  # noqa: E402
from trajjudge.adapter import adapt_trace  # noqa: E402
from trajjudge.agreement import THRESHOLDS  # noqa: E402
from trajjudge.analysis import cluster_interval, join_labels  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.judging import latest_rows, load_rows  # noqa: E402
from trajjudge.robustness import FLOAT_TOL, draw_score, parse_tag  # noqa: E402

from phase3_analysis import scenario_variants  # noqa: E402

OBJECTIVES: tuple[tuple[str, float | None], ...] = (("balanced", None),) + tuple(
    (f"miss_{t:.2f}", t) for t in cal.MISS_RATES)
BINARY_ONLY = "不适用（二值 rubric，无连续分数）"


def with_scenarios(rows: Sequence[Mapping[str, Any]], mapping: Mapping[str, str]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        out.append({**row, "scenario_id": mapping[row["task_id"]]})
    return out


def at_default(rows: Sequence[Mapping[str, Any]], grader: str) -> list[dict[str, Any]]:
    """Out-of-fold-shaped rows predicted at the frozen upstream default, no calibration."""
    out = []
    for row in rows:
        score = row["scores"].get(grader)
        if score is None:
            continue
        out.append({"trace_id": row["trace_id"], "task_id": row["task_id"],
                    "scenario_id": row["scenario_id"], "human": bool(row["human"]),
                    "official": bool(row["official"]), "score": score,
                    "pred": score >= THRESHOLDS[grader],
                    "threshold": f"threshold:{THRESHOLDS[grader]}", "fallback": False})
    return out


def _binary_intervals(rows: Sequence[Mapping[str, Any]], truth: Sequence[bool], pred: Sequence[bool],
                      *, resamples: int, seed: int) -> dict[str, Any]:
    frame = [{"scenario_id": r["scenario_id"], "human": t, "pred": p}
             for r, t, p in zip(rows, truth, pred, strict=True)]
    stats = {
        "accuracy": lambda d: m.accuracy([x["human"] for x in d], [x["pred"] for x in d]) if d else None,
        "kappa": lambda d: m.cohen_kappa([x["human"] for x in d], [x["pred"] for x in d]) if d else None,
        "pabak": lambda d: m.pabak([x["human"] for x in d], [x["pred"] for x in d]) if d else None,
        "balanced_accuracy": lambda d: cal.binary_metrics([x["human"] for x in d], [x["pred"] for x in d])["balanced_accuracy"] if d else None,
        "sensitivity": lambda d: cal.binary_metrics([x["human"] for x in d], [x["pred"] for x in d])["sensitivity"] if d else None,
        "specificity": lambda d: cal.binary_metrics([x["human"] for x in d], [x["pred"] for x in d])["specificity"] if d else None,
        "miss_rate": lambda d: cal.binary_metrics([x["human"] for x in d], [x["pred"] for x in d])["miss_rate"] if d else None,
    }
    return {name: cluster_interval(frame, [x["scenario_id"] for x in frame], stat,
                                   resamples=resamples, seed=seed) for name, stat in stats.items()}


def framework_summary(rows: Sequence[Mapping[str, Any]], *, resamples: int = 2000,
                      seed: int = 0) -> dict[str, Any]:
    """The executable rubric is binary: AUC and PR-AUC are refused, not filled with 0.5."""
    usable = [r for r in rows if r["scores"].get("trajectory_accuracy") is not None]
    truth = [bool(r["human"]) for r in usable]
    pred = [bool(r["official"]) for r in usable]
    base = cal.binary_metrics(truth, pred)
    return {"n": len(usable), "n_scenario": len({r["scenario_id"] for r in usable}),
            "case_study": len({r["scenario_id"] for r in usable}) < cal.MIN_SCENARIOS,
            **base, "auc_pass": None, "auc_fail": None, "pr_auc_fail": None,
            "auc_reason": BINARY_ONLY, "pr_auc_reason": BINARY_ONLY,
            "baselines": m.baselines(truth, seed=seed) if truth else None,
            "intervals": _binary_intervals(usable, truth, pred, resamples=resamples, seed=seed)}


def _arms(result: Mapping[str, Any], *, resamples: int, seed: int) -> dict[str, Any]:
    """Calibrated-only is primary; the fallback-inclusive pool is a sensitivity arm."""
    oof = result["oof"]
    calibrated = [r for r in oof if not r["fallback"]]
    return {
        "grader": result["grader"], "target_miss": result["target_miss"],
        "n_folds": result["n_folds"], "undefined_folds": result["undefined_folds"],
        "undefined_share": result["undefined_share"], "fallback_folds": result["fallback_folds"],
        "folds": result["folds"],
        "calibrated_only": {"n_oof": len(calibrated), **cal.summarize(calibrated, resamples=resamples, seed=seed)},
        "with_fallback": {"n_oof": len(oof), **cal.summarize(oof, resamples=resamples, seed=seed)},
        "thresholds_selected": dict(Counter(f["threshold"] for f in result["folds"])),
    }


def calibration_block(rows: Sequence[Mapping[str, Any]], *, resamples: int = 2000,
                      seed: int = 0) -> dict[str, Any]:
    plan = cal.fold_plan(rows, {r["trace_id"]: r["scenario_id"] for r in rows})
    out: dict[str, Any] = {"n_scenario": len(plan), "n_traj": len(rows), "graders": {}}
    for grader in THRESHOLDS:
        per_grader: dict[str, Any] = {"default_threshold": cal.summarize(at_default(rows, grader),
                                                                       resamples=resamples, seed=seed),
                                      "objectives": {}}
        for name, target in OBJECTIVES:
            per_grader["objectives"][name] = _arms(cal.out_of_fold(plan, grader, target_miss=target),
                                                   resamples=resamples, seed=seed)
        out["graders"][grader] = per_grader
    return out


def load_cache(cache_dir: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(cache_dir.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        parts = parse_tag(entry.get("tag", ""))
        if parts is None or parts["phase"] != "p2" or parts["grader"] not in THRESHOLDS:
            continue
        entries.append({**entry, "parts": parts, "file": path.name})
    return entries


def recover_raw(rows: Sequence[Mapping[str, Any]], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Recover each row's raw completion, proving identity by tokens and score.

    A tag is provenance, not identity: reruns leave several entries under one tag.
    Only an entry whose token totals match the recorded usage *and* whose recomputed
    score matches the recorded score is accepted. Anything else is reported as
    unrecoverable rather than guessed.
    """
    pool: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for entry in entries:
        p = entry["parts"]
        key = (p["trace_id"], p["variant"], p["grader"], p["thinking"], p["repeat_id"], entry.get("model"))
        pool.setdefault(key, []).append(entry)
    out: dict[str, Any] = {}
    for row in rows:
        key = (row["trace_id"], row.get("variant", "original"), row["grader"],
               bool(row.get("thinking")), row["repeat_id"], row.get("judge_model"))
        usage = row.get("usage") or {}
        verified = []
        for entry in pool.get(key, []):
            if (entry.get("prompt_tokens") != usage.get("prompt_tokens")
                    or entry.get("completion_tokens") != usage.get("completion_tokens")):
                continue
            try:
                if abs(draw_score(row["grader"], entry["text"]) - row["score"]) > FLOAT_TOL:
                    continue
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
            verified.append(entry)
        texts = {e["text"] for e in verified}
        record: dict[str, Any] = {"trace_id": row["trace_id"], "grader": row["grader"],
                                  "score": row["score"], "status": row.get("status"),
                                  "candidates": len(pool.get(key, [])), "verified": len(verified)}
        if len(texts) == 1:
            raw = json.loads(verified[0]["text"])
            record.update({"recovered": True, "cache_file": verified[0]["file"], "raw": raw,
                           "comment": row.get("reason")})
        else:
            record.update({"recovered": False,
                           "reason": "原始输出不可得" if not verified else
                           f"原始输出不可得（{len(texts)} 条缓存通过身份校验但内容不同）"})
        out[f"{row['trace_id']}|{row['grader']}"] = record
    return out


def trace_evidence(item: Mapping[str, Any], *, max_chars: int = 700) -> list[dict[str, Any]]:
    """Message-numbered excerpts using the same indexing as the annotation views."""
    trace = adapt_trace(Path(item["trace"]), sidecar_path=Path(item["sidecar"]) if item.get("sidecar") else None)
    out = []
    for index, message in enumerate(trace.messages):
        content = str(message.get("content") or "")
        calls = [c.get("function", {}).get("name") for c in message.get("tool_calls") or []]
        out.append({"index": index, "role": message.get("role", "?"),
                    "tool_calls": [c for c in calls if c],
                    "chars": len(content), "excerpt": content[:max_chars]})
    return out


def hard_sample_block(joined: Sequence[Mapping[str, Any]], items: Mapping[str, Mapping[str, Any]],
                      raw: Mapping[str, Any], labels: Sequence[Mapping[str, str]],
                      key: Mapping[str, str], mapping: Mapping[str, str]) -> dict[str, Any]:
    hard = cal.hard_samples(joined)
    blind_of = {trace: blind for trace, blind in key.items()}
    reason_of = {r["blind_id"]: r.get("reason") or "" for r in labels if r.get("round", "1") == "1"}
    records = []
    for row in hard:
        trace_id = row["trace_id"]
        item = items.get(trace_id)
        evidence = trace_evidence(item) if item else []
        per_grader = {}
        for grader in THRESHOLDS:
            record = raw.get(f"{trace_id}|{grader}")
            per_grader[grader] = record or {"recovered": False, "reason": "原始输出不可得（无缓存记录）"}
        records.append({
            "blind_id": blind_of.get(trace_id), "trace_id": trace_id, "task_id": row["task_id"],
            "scenario_id": mapping[row["task_id"]], "human": row["human"], "official": row["official"],
            "scores": row["scores"], "human_reason_available": bool(reason_of.get(blind_of.get(trace_id, ""))),
            "evidence": evidence, "graders": per_grader,
            "evidence_available": bool(evidence),
        })
    scenarios = sorted({r["scenario_id"] for r in records})
    return {"status": "provisional", "definition": "human fail ∧ framework passed ∧ accuracy ≥ 2.0 ∧ comprehensive ≥ 0.6",
            "n_traj": len(records), "n_scenario": len(scenarios), "scenarios": scenarios,
            "case_study": len(scenarios) < cal.MIN_SCENARIOS, "records": records,
            "note": "人工理由原文不入库；本文件含 trace_id 与评分器原话，按 owner 裁定只留本地"}


def hybrid_block(joined: Sequence[Mapping[str, Any]], key: Mapping[str, str]) -> dict[str, Any]:
    ev = cal.hybrid_evidence(joined)
    # A trace id would let a reader locate the exact trajectory behind a human
    # label. The blind id is the annotation-safe identifier and its key stays
    # local, so the tracked aggregate never carries trace ids. An unmapped trace
    # raises rather than silently falling back to the raw id.
    blind_of = {trace: blind for trace, blind in key.items()}
    for field in ("framework_only", "graders_only", "neither", "both"):
        ev[field] = sorted(blind_of[trace] for trace in ev[field])
    n = ev["n_human_fail"]
    rates = [v for v in ev["miss_rate"].values() if v is not None]
    support = bool(n and rates and ev["miss_rate_union"] is not None
                   and (ev["framework_only"] or ev["graders_only"])
                   and ev["miss_rate_union"] < min(rates))
    against = bool(n and ev["framework_false_fail_on_human_pass"] > max(ev["grader_false_fail_on_human_pass"].values()))
    if ev["n_scenario_fail"] < cal.MIN_SCENARIOS:
        verdict = "证据不足，不下结论"
        reason = f"human fail 只覆盖 {ev['n_scenario_fail']} 个独立场景（< {cal.MIN_SCENARIOS}），按 §3 属 case study"
    elif support and against:
        verdict = "支持与反对证据并存，不下结论"
        reason = "并集漏判率更低，但 framework 在 human pass 上的误杀也更多；两者必须并列"
    elif support:
        verdict = "有支持证据"
        reason = "framework 与 grader 的漏判集合不重合，且并集漏判率低于任一单独漏判率"
    elif against:
        verdict = "有反对证据"
        reason = "framework 在 human pass 上的误杀多于 grader，并集未降低漏判率"
    else:
        verdict = "证据不足，不下结论"
        reason = "支持与反对判据都不成立"
    return {**ev, "support": support, "against": against, "verdict": verdict, "verdict_reason": reason,
            "rule": "PREREG_v2 §7b：支持=漏判集合不重合且并集更优；反对=framework 误杀更多或增益不抵误杀"}


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{0.0 if value == 0 else value:.{digits}f}"
    return str(value)


def _ci(interval: Mapping[str, Any] | None) -> str:
    if not interval:
        return "—"
    ci = interval.get("ci")
    if ci is None:
        return f"{interval.get('status', 'not_estimable')}（{interval.get('reason', '')}）"
    return f"[{ci[0]:.4f}, {ci[1]:.4f}]"


def _escape(text: Any) -> str:
    return str(text).replace("|", "\\|")


def _auc_verdict(entry: Mapping[str, Any]) -> str:
    """Three states, not two: an unestimable CI is not evidence of discrimination.

    Rendering ``not_estimable`` as "否" would repeat the v1 error of reading a
    missing interval as a precise result (PREREG_v2 §2 forbids substituting a
    point estimate for an interval that could not be estimated).
    """
    covers = entry.get("auc_covers_half")
    if covers is None:
        return "不可估（簇数不足）→ 不得据此声称区分度"
    return "是 → 无证据支持可用区分度" if covers else "否"


def markdown(block: Mapping[str, Any], framework: Mapping[str, Any], hard: Mapping[str, Any],
             hybrid: Mapping[str, Any], joined: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 4 — 阈值校准与饱和处理（PROVISIONAL / exploratory）",
        "",
        "> **PROVISIONAL**：依赖 round1 人工标签，闸门 A 未通过。按 PREREG_v2 §7/§7b 全部标 **exploratory**，",
        "> **不得**写入 `FINAL_REPORT_v2.md` 或 `RESUME_CLAIMS.md`。若人类 test-retest κ < 0.60，永久降级为 exploratory。",
        "> 评分器原话与逐轨迹明细只在 `reports/` 内；round2 完成前不得进入 `GUIDE.md`、kit 或任何标注视图。",
        "",
        "## 1. 样本与场景口径",
        "",
        f"- 已连接标签轨迹 **{joined['labeled']}**（候选 {joined['selected']}），"
        f"缺失分数：{joined['missing_scores']}。",
        f"- 独立场景 **{block['merge']['n_scenario']}**（merge 主口径）/ "
        f"**{block['split']['n_scenario']}**（split 敏感性口径）。",
        "- LOSO：每折留出**整个场景**，译本孪生同折；阈值只在训练折上选，指标只由 out-of-fold 预测池化后计算。",
        "",
        "## 2. 上游默认阈值下的三者对比（framework rubric vs 两个 LLM grader）",
        "",
        "| 评分器 | n | 场景 | accuracy | κ | PABAK | balanced acc | 漏判率 | AUC(pass) | PR-AUC(fail) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, entry in (("framework rubric（可执行检查）", framework),
                        *((g, block["merge"]["graders"][g]["default_threshold"]) for g in THRESHOLDS)):
        lines.append(
            f"| {_escape(name)} | {entry.get('n', 0)} | {entry.get('n_scenario', 0)} | {_fmt(entry.get('accuracy'))} | "
            f"{_fmt(entry.get('kappa'))} | {_fmt(entry.get('pabak'))} | {_fmt(entry.get('balanced_accuracy'))} | "
            f"{_fmt(entry.get('miss_rate'))} | {_fmt(entry.get('auc_pass'))} | {_fmt(entry.get('pr_auc_fail'))} |")
    lines += [
        "",
        f"- framework 的 AUC / PR-AUC：**{BINARY_ONLY}**，不填 0.5。",
        "- 漏判率 = human fail 中被判 pass 的比例；正类 = pass，故漏判 = false positive。",
        "",
        "### 2b. 区间（scenario 簇 bootstrap，B=2000、percentile 95%、seed=0）",
        "",
        "| 评分器 | 指标 | 点估计 | 95% CI | 状态 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for name, entry in (("framework", framework),
                        *((g, block["merge"]["graders"][g]["default_threshold"]) for g in THRESHOLDS)):
        for stat in ("accuracy", "kappa", "balanced_accuracy", "miss_rate", "auc_pass", "pr_auc_fail"):
            interval = (entry.get("intervals") or {}).get(stat)
            lines.append(f"| {_escape(name)} | {stat} | {_fmt(entry.get(stat))} | {_ci(interval)} | "
                         f"{_escape((interval or {}).get('status', '—'))} |")
    lines += ["", "## 3. LOSO 阈值校准（主指标 = balanced accuracy）", ""]
    for variant in ("merge", "split"):
        lines += [f"### 3.{1 if variant == 'merge' else 2} `{variant}`"
                  f"{'（主口径）' if variant == 'merge' else '（敏感性口径）'}", "",
                  "| grader | 目标 | 折数 | 未定义折 | 选出阈值（计数） | OOF n | κ | balanced acc | 漏判率 | AUC | AUC CI 覆盖 0.5 |",
                  "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
        for grader in THRESHOLDS:
            for name, _ in OBJECTIVES:
                arm = block[variant]["graders"][grader]["objectives"][name]
                primary = arm["calibrated_only"]
                thresholds = ", ".join(f"{_escape(k)}×{v}" for k, v in sorted(arm["thresholds_selected"].items()))
                lines.append(
                    f"| {_escape(grader)} | {name} | {arm['n_folds']} | {arm['undefined_folds']} | {thresholds} | "
                    f"{primary['n']} | {_fmt(primary.get('kappa'))} | {_fmt(primary.get('balanced_accuracy'))} | "
                    f"{_fmt(primary.get('miss_rate'))} | {_fmt(primary.get('auc_pass'))} | "
                    f"{_auc_verdict(primary)} |")
        lines.append("")
    lines += [
        "**两臂并列**（§7b）：`calibrated_only` 为主指标池；`with_fallback` 含未定义折改用上游默认阈值的预测，"
        "只作敏感性臂。未定义折不得静默丢弃。",
        "",
        "| 口径 | grader | 目标 | 臂 | OOF n | 未定义折占比 | accuracy | κ | specificity | 漏判率 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in ("merge", "split"):
        for grader in THRESHOLDS:
            for name, _ in OBJECTIVES:
                arm = block[variant]["graders"][grader]["objectives"][name]
                for arm_name in ("calibrated_only", "with_fallback"):
                    entry = arm[arm_name]
                    lines.append(
                        f"| {variant} | {_escape(grader)} | {name} | {arm_name} | {entry['n']} | "
                        f"{_fmt(arm['undefined_share'])} | {_fmt(entry.get('accuracy'))} | {_fmt(entry.get('kappa'))} | "
                        f"{_fmt(entry.get('specificity'))} | {_fmt(entry.get('miss_rate'))} |")
    lines += [
        "",
        "### 3b. 固定漏判率下的 specificity（主值 0.25）",
        "",
        "选点规则（§7b 冻结）：训练折上取 `train_miss_rate ≤ target` 中最接近 target 的网格点，"
        "并列取更接近上游默认阈值；`always_fail` 漏判率为 0，故任何非负 target 都可满足。",
        "",
        "| 口径 | grader | target | 选出阈值 | OOF specificity | specificity CI | OOF sensitivity | 漏判率 | 未定义折 |",
        "| --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for variant in ("merge", "split"):
        for grader in THRESHOLDS:
            for target in cal.MISS_RATES:
                arm = block[variant]["graders"][grader]["objectives"][f"miss_{target:.2f}"]
                entry = arm["calibrated_only"]
                thresholds = ", ".join(f"{_escape(k)}×{v}" for k, v in sorted(arm["thresholds_selected"].items()))
                lines.append(f"| {variant} | {_escape(grader)} | {target:.2f}{'（主值）' if target == cal.PRIMARY_MISS_RATE else ''} | "
                             f"{thresholds} | {_fmt(entry.get('specificity'))} | "
                             f"{_ci((entry.get('intervals') or {}).get('specificity'))} | "
                             f"{_fmt(entry.get('sensitivity'))} | {_fmt(entry.get('miss_rate'))} | {arm['undefined_folds']} |")
    degenerate = sorted({(variant, grader, f"miss_{t:.2f}")
                         for variant in ("merge", "split") for grader in THRESHOLDS for t in cal.MISS_RATES
                         if set(block[variant]["graders"][grader]["objectives"][f"miss_{t:.2f}"]["thresholds_selected"])
                         <= set(cal.SENTINELS)})
    if degenerate:
        lines += ["", "**退化警告（必须与上表一起读）**：以下单元只能靠哨兵策略达到目标漏判率 —— "
                  + "；".join(f"{v}/{g}/{o}" for v, g, o in degenerate) + "。",
                  "`always_fail` 的 specificity = 1、漏判率 = 0，但它把**全部** human pass 也判 fail"
                  "（sensitivity = 0）。这不是可用的校准，而是「拒绝一切」的退化解；"
                  "不得把它的 specificity 当作评分器区分度的证据。"]
    lines += [
        "",
        "## 4. 硬样本子集（饱和的正面证据）",
        "",
        f"- 定义（§7 冻结）：{hard['definition']}。",
        f"- **n_traj = {hard['n_traj']}，n_scenario = {hard['n_scenario']}**"
        f"{'；**case study**（场景数 < 5），不出百分比结论句' if hard['case_study'] else ''}。",
        f"- 场景：{', '.join(hard['scenarios']) or '（无）'}。",
        "- 逐轨迹理由类别、轨迹证据与 grader 原话摘录见 `reports/failure_taxonomy.md`；"
        "含 trace_id 的明细只在本地 `reports/phase4_hard_samples.json`（**不入库**）。",
        "",
        "## 5. 混合评分（可执行检查 + LLM judge）的证据",
        "",
        f"- human fail **{hybrid['n_human_fail']}** 条，覆盖 **{hybrid['n_scenario_fail']}** 个独立场景；"
        f"human pass {hybrid['n_human_pass']} 条。",
        f"- 抓到数：framework {hybrid['caught_by']['framework']}，"
        + "，".join(f"{g} {hybrid['caught_by'][g]}" for g in THRESHOLDS)
        + f"；并集 {hybrid['caught_union']}。",
        f"- 漏判率：framework {_fmt(hybrid['miss_rate']['framework'])}，"
        + "，".join(f"{g} {_fmt(hybrid['miss_rate'][g])}" for g in THRESHOLDS)
        + f"；并集 {_fmt(hybrid['miss_rate_union'])}。",
        f"- 分解：仅 framework 抓到 {len(hybrid['framework_only'])}，仅 grader 抓到 {len(hybrid['graders_only'])}，"
        f"两者都抓到 {len(hybrid['both'])}，都漏 {len(hybrid['neither'])}。",
        f"- **效应量（必须与判读一起读）**：并集比最好的单独评分器多抓 "
        f"{hybrid['caught_union'] - max(hybrid['caught_by'].values())} 条 human fail"
        f"（{max(hybrid['caught_by'].values())}/{hybrid['n_human_fail']} → "
        f"{hybrid['caught_union']}/{hybrid['n_human_fail']}）。"
        "增益以条数计，不以百分比结论句表述。",
        f"- human pass 上的误杀（判 fail）：framework {hybrid['framework_false_fail_on_human_pass']}，"
        + "，".join(f"{g} {hybrid['grader_false_fail_on_human_pass'][g]}" for g in THRESHOLDS) + "。",
        f"- **判读：{hybrid['verdict']}** —— {hybrid['verdict_reason']}。",
        f"- 判读规则：{hybrid['rule']}。",
        "",
        "## 6. 限制（只写真实的）",
        "",
        f"- 单一 judge 模型（deepseek-flash）、`thinking=off`、`direct`、repeat 0、未防御臂；"
        f"标签来自单一标注者的 round1，**闸门 A 未通过**。",
        f"- 独立场景 {block['merge']['n_scenario']} 个（merge）；hard sample 只有 {hard['n_scenario']} 个场景。",
        "- 阈值网格与目标函数在 §7/§7b 冻结，**未**在看到结果后调整；本阶段全部 exploratory。",
        "- comprehensive 分数顶格（v1 最低 0.6354、100% ≥ 0.6）：降低阈值换召回必然牺牲 specificity，"
        "校准不能凭空创造区分度。",
        "- 新增 API 调用 **0**，新增花费 **$0.00**；原始输出全部由 `.cache/llm` 离线恢复并通过 token+分数身份校验。",
        "",
        "## 7. 复算",
        "",
        "```bash",
        ".venvs/judge/bin/python scripts/phase4_analysis.py --resamples 2000 --seed 0",
        ".venvs/judge/bin/python -m pytest tests/test_calibration.py tests/test_phase4_analysis.py",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grades", type=Path, default=root / "outputs/p2/p2-deepseek-flash.jsonl")
    parser.add_argument("--meta", type=Path, default=root / "outputs/p2/annotation_meta.json")
    parser.add_argument("--frozen", type=Path, default=root / "outputs/p2/annotation_set.json")
    parser.add_argument("--key", type=Path, default=root / "outputs/annotation/key.json")
    parser.add_argument("--labels", type=Path, default=root / "annotation/labels.csv")
    parser.add_argument("--scenario-map", type=Path, default=root / "reports/scenario_map.csv")
    parser.add_argument("--uncertain", type=Path, default=root / "reports/scenario_map_uncertain.json")
    parser.add_argument("--cache", type=Path, default=root / ".cache/llm")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    variants = scenario_variants(args.scenario_map, args.uncertain)
    meta = json.loads(args.meta.read_text(encoding="utf-8"))
    key = json.loads(args.key.read_text(encoding="utf-8"))
    labels = kit.read_labels(args.labels)
    grades = latest_rows(load_rows(args.grades))
    joined = join_labels(meta["chosen"], key, labels, grades)

    entries = load_cache(args.cache)
    raw = recover_raw(grades, entries)
    items = {item["trace_id"]: item for item in json.loads(args.frozen.read_text(encoding="utf-8"))}

    block: dict[str, Any] = {}
    framework: dict[str, Any] = {}
    hybrid: dict[str, Any] = {}
    for name in ("merge", "split"):
        rows = with_scenarios(joined["rows"], variants[name])
        block[name] = calibration_block(rows, resamples=args.resamples, seed=args.seed)
        if name == "merge":
            framework = framework_summary(rows, resamples=args.resamples, seed=args.seed)
            hybrid = hybrid_block(rows, key)
            hard = hard_sample_block(rows, items, raw, labels, key, variants[name])

    recovered = sum(r["recovered"] for r in raw.values())
    payload = {"status": "provisional", "status_note": "exploratory；闸门 A 未通过，不得升级为 confirmatory",
               "primary_variant": "merge", "scenario_variant_flagged": variants["flagged"],
               "joined": {k: joined[k] for k in ("labeled", "selected", "missing_scores")},
               "calibration": block, "framework": framework, "hybrid_scoring": hybrid,
               "hard_samples": {k: hard[k] for k in ("definition", "n_traj", "n_scenario", "scenarios", "case_study")},
               "raw_recovery": {"rows": len(raw), "recovered": recovered,
                                "unrecoverable": sorted(k for k, r in raw.items() if not r["recovered"]),
                                "api_calls": 0, "new_cost_usd": 0.0}}
    atomic_text(root / "reports/phase4_calibration.json", json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    atomic_text(root / "reports/phase4_hard_samples.json", json.dumps(hard, ensure_ascii=False, indent=1) + "\n")
    atomic_text(root / "reports/phase4_provisional.md", markdown(block, framework, hard, hybrid, joined))

    print(f"[PROVISIONAL] 已连接 {joined['labeled']} 条标签；场景 merge {block['merge']['n_scenario']} / "
          f"split {block['split']['n_scenario']}")
    print(f"[PROVISIONAL] 原始输出恢复 {recovered}/{len(raw)}（token+分数双重校验），新增 API 调用 0，花费 $0.00")
    print(f"[PROVISIONAL] 硬样本 n_traj={hard['n_traj']} n_scenario={hard['n_scenario']}"
          f"{'（case study）' if hard['case_study'] else ''}")
    print(f"[PROVISIONAL] 混合评分判读：{hybrid['verdict']}")
    for grader in THRESHOLDS:
        entry = block["merge"]["graders"][grader]["objectives"]["balanced"]["calibrated_only"]
        print(f"[PROVISIONAL] {grader}: OOF AUC={_fmt(entry.get('auc_pass'))} "
              f"CI={_ci((entry.get('intervals') or {}).get('auc_pass'))} "
              f"覆盖0.5={entry.get('no_usable_discrimination')}")
    print("written: reports/phase4_calibration.json, reports/phase4_hard_samples.json, reports/phase4_provisional.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())