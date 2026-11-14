#!/usr/bin/env python
"""Emit reports/v1_vs_v2_stats.md from the paired v1/v2 report JSONs. Local evidence only."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text

RUNS = ("flash-strategies-4", "pro-direct-4", "flash-direct-pilot")


def load(name: str) -> dict:
    return json.loads((root / "reports" / f"{name}.json").read_text(encoding="utf-8"))


def fmt(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(fmt(v, digits) for v in value) + "]"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def width(ci) -> str:
    return "—" if not ci else f"{ci[1] - ci[0]:.4f}"


def cell(text) -> str:
    """Config names contain '|', which would otherwise split the markdown table."""
    return str(text).replace("|", "\\|")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "reports/v1_vs_v2_stats.md")
    args = parser.parse_args()

    p2v1, p2v2 = load("p2")["agreement"], load("p2-v2")["agreement"]
    p4v1, p4v2 = load("p4")["analysis"], load("p4-v2")["analysis"]
    rob = load("robustness_v2")
    lines: list[str] = []
    add = lines.append

    add("# v1 ↔ v2 统计口径对照")
    add("")
    add("本文件由 `scripts/v2_stats_compare.py` 从已落盘的报告 JSON 生成，不含任何新实验。")
    add("v1 = 已发布口径（task_id 簇、丢弃未定义抽样、允许零宽 CI）；v2 = `docs/PREREG_v2.md` 口径。")
    add("两者读取**同一批原始行**，差异只来自统计定义，不来自数据。")
    add("")
    add("## 1. 口径变更清单")
    add("")
    add("| 项目 | v1 | v2 |")
    add("| --- | --- | --- |")
    add("| 自助聚类单元 | task_id（中英译本算两个独立单元） | scenario_id（译本合并） |")
    add("| 未定义自助抽样 | 静默丢弃，不足半数才返回 null | 计数并报告占比，>10% 判 unreliable |")
    add("| 零宽 CI | 直接输出，如 `[0.0, 0.0]` | 拒绝，输出「不可估（簇数不足）」 |")
    add("| 翻转率分母 | 基线失败的**观测对** | 基线失败的**不同轨迹**，并报告 n_traj/n_scenario/pairs |")
    add("| 少场景翻转率 | 照常给百分比 | n_scenario<5 判 case study，不给百分比结论 |")
    add("| 注入主指标 | 翻转率 | ASR（分数上升率）为主，判定翻转另列 |")
    add("| 翻转方向 | 只统计 fail→pass | fail→pass 与 pass→fail 分别统计 |")
    add("| strategy 对比 | 称作三种独立策略 | 共享采样的聚合函数对比 |")
    add("| 缺失处理 | 排除后不报告影响 | 分层缺失率 + invalid 当 pass/当 fail 敏感性 |")
    add("")

    add("## 2. RQ1 一致性（P2，人工标签 48 条）")
    add("")
    add(f"自助簇数：**{p2v1['bootstrap_clusters']} → {p2v2['bootstrap_clusters']}**。")
    add("")
    add("| 评分器 | 指标 | v1 CI | v1 宽度 | v2 CI | v2 宽度 | v2 状态 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for grader in p2v1["graders"]:
        for metric in ("accuracy", "kappa", "auc"):
            a, b = p2v1["graders"][grader], p2v2["graders"][grader]
            iv = b.get(f"{metric}_interval") or {}
            add(f"| {grader} | {metric} | {fmt(a.get(metric + '_ci'))} | {width(a.get(metric + '_ci'))} "
                f"| {fmt(b.get(metric + '_ci'))} | {width(b.get(metric + '_ci'))} | {iv.get('status', '—')} |")
    add("")
    add("注意：scenario 聚类**没有让所有区间变宽**。译本成对进入同一簇后，标签比例在重采样中更稳定，")
    add("accuracy 的 κ 区间反而收窄。伪重复的危害不是单向放大区间，而是让区间宽度失去解释力。")
    add("两个评分器的 κ 区间都覆盖 0，「与人工判定无超出偶然的一致」这一结论在 v2 下不变。")
    add("")

    add("## 3. RQ2 稳定性（P3）")
    add("")
    add("| 运行 | 配置 | 簇数 v1→v2 | flip_rate | v1 CI | v2 CI | v2 状态 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    zero_width = total = widened = 0
    for run in RUNS:
        v1, v2 = load(f"p3-v1-{run}")["analysis"], load(f"p3-v2-{run}")["analysis"]
        for a, b in zip(v1, v2):
            if not a["summary"]:
                continue
            total += 1
            c1, c2 = a["ci"].get("flip_rate"), b["ci"].get("flip_rate")
            if c1 and c1[0] == c1[1]:
                zero_width += 1
            if c1 and c2 and (c2[1] - c2[0]) > (c1[1] - c1[0]):
                widened += 1
            status = (b.get("intervals", {}).get("flip_rate") or {}).get("status", "—")
            add(f"| {run} | `{cell(a['config'][0])}` | {a.get('bootstrap_clusters')}→{b.get('bootstrap_clusters')} "
                f"| {fmt(a['summary']['flip_rate'], 3)} | {fmt(c1)} | {fmt(c2)} | {status} |")
    add("")
    add(f"共 {total} 个完整配置：v1 有 **{zero_width} 个零宽 flip CI**，v2 全部改判「不可估（簇数不足）」；")
    add(f"其余 {widened} 个非零宽区间在 v2 下**变宽**。")
    add("「多数配置 flip_rate=0」在 v1 里读作「精确为零」，在 v2 里只能读作「簇数不足以估计」。")
    add("")

    add("## 4. RQ3 注入（P4，16 条轨迹 / 11 个场景）")
    add("")
    case = sum(e["case_study"] for e in p4v2)
    add(f"- 配对观测 **{sum(e['paired_observations'] for e in p4v2)}**，未配对 **{sum(e['unpaired_observations'] for e in p4v2)}**（invalid 保留，不补零）。")
    add(f"- 32 个 (配置×变体) 条目中 **{case} 个判为 case study**：基线失败只落在 1 条轨迹 / 1 个场景上。")
    add(f"- fail→pass **{sum(e['fail_to_pass_observations'] for e in p4v2)}** 次，pass→fail **{sum(e['pass_to_fail_observations'] for e in p4v2)}** 次，"
        f"判定改变合计 **{sum(e['verdict_changed_observations'] for e in p4v2)}** 次。v1 只报告了前者。")
    add(f"- ASR>0 的条目 **{sum((e['asr'] or 0) > 0 for e in p4v2)}/32**；ASR 自助簇数 **{p4v2[0]['bootstrap_clusters']}**（场景）。")
    add("")
    add("### 4.1 主指标 ASR（综合评分器，未防御 / 防御）")
    add("")
    add("| 变体 | 未防御 ASR | 95% CI | 防御 ASR | 95% CI | 差值 |")
    add("| --- | --- | --- | --- | --- | --- |")
    comp = {(e["variant"], e["config"][0].endswith("|def")): e for e in p4v2
            if e["grader"] == "trajectory_comprehensive"}
    for variant in sorted({v for v, _ in comp}):
        u, d = comp.get((variant, False)), comp.get((variant, True))
        if not u or not d:
            continue
        add(f"| {variant} | {fmt(u['asr'])} | {fmt(u['asr_ci'])} | {fmt(d['asr'])} | {fmt(d['asr_ci'])} "
            f"| {fmt(u['asr'] - d['asr'])} |")
    add("")
    add("### 4.2 被 v1 掩盖的方向性")
    add("")
    add("| 评分器 | 防御 | fail→pass | pass→fail |")
    add("| --- | --- | --- | --- |")
    for grader in sorted({e["grader"] for e in p4v2}):
        for defended in (False, True):
            sub = [e for e in p4v2 if e["grader"] == grader and e["config"][0].endswith("|def") is defended]
            add(f"| {grader} | {'是' if defended else '否'} | {sum(e['fail_to_pass_observations'] for e in sub)} "
                f"| {sum(e['pass_to_fail_observations'] for e in sub)} |")
    add("")
    add("综合评分器的判定翻转在观测臂为 0：基线分全部 ≥0.6（饱和），注入后仍 ≥0.6。")
    add("因此「注入改变判定」的证据全部来自 accuracy，且集中在单一场景，只能作为个案。")
    add("")

    agg = rob["aggregation"]
    add("## 5. 共享采样的聚合函数对比（PREREG_v2 §4）")
    add("")
    rl, dl = agg["row_level"], agg["draw_level"]
    add(f"- 抽样共享：{rl['shared_token_panels']}/{rl['ok_average_voting_pairs']} 个 voting 面板与 average **token 完全一致**，"
        f"且 {rl['voting_zero_new_calls']}/{rl['ok_average_voting_pairs']} 个 voting **新增 API 调用为 0**。")
    add(f"- 逐抽样恢复：{agg['recovery']['verified']}/{agg['recovery']['panels_seen']} 个面板"
        f"（覆盖率 {fmt(agg['recovery']['coverage'])}），每个都同时复现了已记录的 average 与 voting 分数。")
    add(f"- 不可恢复面板 {len(agg['recovery']['excluded'])} 个，原因逐条列于 `reports/robustness_v2.json`，未做任何填补。")
    add("")
    add("| 指标 | 全体 | accuracy | comprehensive |")
    add("| --- | --- | --- | --- |")
    for key, label in (("all_draws_distinct", "三次抽样互不相同"),
                       ("voting_eq_min", "voting == min(三次)"),
                       ("voting_lt_average", "voting < average")):
        cells = []
        for scope in (dl, dl["by_grader"].get("trajectory_accuracy", {}), dl["by_grader"].get("trajectory_comprehensive", {})):
            n = scope.get("panels")
            cells.append(f"{scope.get(key, 0)}/{n}" if n else "—")
        add(f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} |")
    add("")
    add(f"行级（全部 ok 面板，不依赖缓存恢复）：voting < average = **{rl['voting_lt_average']}/{rl['ok_average_voting_pairs']}**，"
        f"其中 comprehensive **{rl['voting_lt_average_by_grader']['trajectory_comprehensive']['voting_lt_average']}"
        f"/{rl['voting_lt_average_by_grader']['trajectory_comprehensive']['pairs']}**，与 v1 报告的 12/22 一致。")
    add("")
    add("结论：voting 不是独立重复实验，而是同一批抽样的众数聚合。两个评分器的退化机制不同：")
    acc = dl["by_grader"]["trajectory_accuracy"]
    cmp_ = dl["by_grader"]["trajectory_comprehensive"]
    add(f"- accuracy：voting==min 高达 {acc['voting_eq_min']}/{acc['panels']}，但三次抽样互不相同为 "
        f"{acc['all_draws_distinct']}/{acc['panels']}——饱和使三次同分，众数与最小值天然相同，不是 tie-break 造成的。")
    add(f"- comprehensive：三次互不相同 {cmp_['all_draws_distinct']}/{cmp_['panels']}，连续分数的浮点尾差让众数不存在，")
    add(f"  上游 `tie_breaker=MIN` 于是直接取最小值，voting==min {cmp_['voting_eq_min']}/{cmp_['panels']}、"
        f"voting<average {cmp_['voting_lt_average']}/{cmp_['panels']}。**这才是 MIN 退化。**")
    add("")

    add("## 6. 缺失机制与敏感性（PREREG_v2 §5）")
    add("")
    miss = rob["missingness"]["p4_injection"]
    add(f"P4 共 {miss['rows']} 行，invalid **{miss['invalid']}** 行（{fmt(miss['invalid_rate'])}）。")
    add("")
    add("| 分层 | 取值 | 行数 | invalid | 缺失率 |")
    add("| --- | --- | --- | --- | --- |")
    for field in ("grader", "defended"):
        for b in miss["strata"][field]:
            add(f"| {field} | {b['value']} | {b['rows']} | {b['invalid']} | {fmt(b['invalid_rate'])} |")
    add("")
    fv = miss["defended_vs_invalid"]
    add(f"防御臂 × invalid 的 Fisher 精确检验 p = **{fmt(fv['fisher_exact_p'])}**（{fv['status']}，未预注册为假设）。")
    by_def = {b["value"]: b for b in miss["strata"]["defended"]}
    by_grader = {b["value"]: b for b in miss["strata"]["grader"]}
    ratio = (by_def[True]["invalid_rate"] / by_def[False]["invalid_rate"]) if by_def[False]["invalid_rate"] else None
    add(f"列联表 {fv['table']}。invalid 按评分器分布："
        + "、".join(f"{g} {b['invalid']}" for g, b in sorted(by_grader.items()))
        + f"；防御臂缺失率是未防御臂的 {fmt(ratio, 1)} 倍。")
    add("这意味着 wrapper 的「防御收益」与「更高的格式失败率」同时发生，必须做敏感性才能分开。")
    add("")
    add("### 6.1 注入敏感性（invalid 当 pass / 当 fail）")
    add("")
    add("| 评分器 / 臂 | observed ASR | invalid_as_pass | invalid_as_fail | observed 排除对 |")
    add("| --- | --- | --- | --- | --- |")
    for key, s in rob["injection_sensitivity"].items():
        arms = s["arms"]
        add(f"| {cell(key)} | {fmt(arms['observed']['asr'])} | {fmt(arms['invalid_as_pass']['asr'])} "
            f"| {fmt(arms['invalid_as_fail']['asr'])} | {arms['observed']['excluded']} |")
    add("")
    add("防御与未防御的 ASR 差在三个臂下都保持同一方向与量级，**防御收益不是缺失数据造成的假象**。")
    excl_u = rob["injection_sensitivity"]["trajectory_comprehensive|defended=False"]["arms"]["observed"]["excluded"]
    excl_d = rob["injection_sensitivity"]["trajectory_comprehensive|defended=True"]["arms"]["observed"]["excluded"]
    add(f"但防御臂被排除的配对数（{excl_d}）约为未防御臂（{excl_u}）的 {fmt(excl_d / excl_u if excl_u else None, 1)} 倍，"
        "覆盖率差异本身必须写进结论限制。")
    add("")
    add("### 6.2 RQ1 敏感性")
    add("")
    add("人工标注帧缺失分数：" + "、".join(f"{g} {n}" for g, n in sorted(rob["missing_scores"].items())) + "。")
    add("两个评分器均为 0，因此三个臂完全重合（`informative=false`）——")
    add("**RQ1 的结论不受缺失影响，敏感性在此不具信息量**，如实记录而非省略。")
    add("")

    add("## 7. 结论变化汇总")
    add("")
    add("| 旧结论 | v2 判定 | 依据 |")
    add("| --- | --- | --- |")
    add("| 注入翻转率 75% | **推翻** | 分母是 1 条轨迹的 3 次重复，n_scenario=1，只能作个案 |")
    add(f"| 多数配置 flip_rate=0（精确） | **削弱** | {zero_width}/{total} 零宽 CI 改判不可估；其余区间变宽至 [0,1] |")
    add("| 50 条样本覆盖 36 个独立任务 | **削弱** | 35 个 task_id 实为 28 个场景，译本伪重复 |")
    add(f"| voting 是独立于 average 的稳定性策略 | **推翻** | {rl['shared_token_panels']}/{rl['ok_average_voting_pairs']} 面板 token 相同、新增调用 0；comprehensive 有 {cmp_['all_draws_distinct']}/{cmp_['panels']} 面板因 MIN tie-break 取最小值 |")
    add("| 评分器与人工一致（accuracy 66.7%） | **不变但需降级** | κ 区间覆盖 0；66.7% 与 always-pass 基线同值 |")
    add("| wrapper 防御有效 | **加强（附条件）** | ASR 差在三个敏感性臂下稳定；但防御臂格式失败率更高 |")
    add("| 缺失可忽略 | **推翻** | 缺失非随机：全部集中于 comprehensive，且防御臂更高 |")
    add("")
    add("## 8. 复现命令")
    add("")
    add("```bash")
    add("PY=.venvs/judge/bin/python")
    add("$PY scripts/report_experiments.py p2 --output-suffix=-v1check   # v1 数值不变（仅新增元数据键）")
    add("$PY scripts/report_experiments.py p2 --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2")
    add("$PY scripts/report_experiments.py p4 --input outputs/p4/p4-flash-human-fail-16.jsonl \\")
    add("    --expected-unlabeled 2 --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2")
    for run in RUNS:
        add(f"$PY scripts/report_experiments.py p3 --input outputs/p3/p3-{run}.jsonl --output-suffix=-v1-{run}")
        add(f"$PY scripts/report_experiments.py p3 --input outputs/p3/p3-{run}.jsonl \\")
        add(f"    --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2-{run}")
    add("$PY scripts/robustness_diagnostics.py")
    add("$PY scripts/v2_stats_compare.py")
    add("```")
    add("")
    atomic_text(args.output, "\n".join(lines))
    print(json.dumps({"output": str(args.output.relative_to(root)) if args.output.is_relative_to(root) else str(args.output),
                      "stability_entries": total, "zero_width_v1": zero_width,
                      "case_study_entries": case}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())