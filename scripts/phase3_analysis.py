#!/usr/bin/env python
"""Phase 3 groundwork and a PROVISIONAL scenario-level injection re-analysis.

Nothing here spends money: the injection grid is verified against an offline cache
replay. Every output that depends on round-1 human labels is marked PROVISIONAL
(PREREG_v2 §6b) and must not reach FINAL_REPORT_v2 or RESUME_CLAIMS before gate A.

The private strata file is read for trace_id/task_id only; framework `passed` and
`task_score` are never used as a substitute for human labels.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge import annotation as kit  # noqa: E402
from trajjudge import scenario_stats as ss  # noqa: E402
from trajjudge.artifacts import atomic_text  # noqa: E402
from trajjudge.judging import latest_rows, load_rows  # noqa: E402

GATE_B_SCENARIOS = 10
VIP_PAIR = ("T159zh_vip_ticket_escalation", "T160_vip_ticket_escalation")


def scenario_variants(map_path: Path, uncertain_path: Path) -> dict[str, dict[str, str]]:
    """Merge is primary; split separates the pairs Phase 0 flagged for owner confirmation."""
    with map_path.open(newline="", encoding="utf-8") as handle:
        merge = {r["task_id"]: r["scenario_id"] for r in csv.DictReader(handle)}
    split = dict(merge)
    flagged = []
    for entry in json.loads(uncertain_path.read_text(encoding="utf-8")):
        if not entry["recommendation"].startswith("owner confirmation required"):
            continue
        tasks = entry["task_ids"]
        flagged.append(tasks)
        for task in tasks:
            split[task] = f"{merge[task]}__{task}"
    return {"merge": merge, "split": split, "flagged": flagged}


def pool_stats(candidates: Sequence[Mapping[str, Any]], chosen: Sequence[Mapping[str, Any]],
               labels: Sequence[Mapping[str, str]], key: Mapping[str, str],
               mapping: Mapping[str, str]) -> dict[str, Any]:
    """Census of the 87 completed trajectories and the human-fail injection candidate pool."""
    blind_of = {blind: trace for trace, blind in key.items()}
    blank_blinds = [r["blind_id"] for r in labels if not r["label"]]
    blanks = {blind_of[b] for b in blank_blinds if b in blind_of}
    labeled = {blind_of[r["blind_id"]] for r in labels if r["label"] and r["blind_id"] in blind_of}
    fail_blinds = {r["blind_id"] for r in labels if r["label"] == "fail"}
    fails = [c for c in chosen if key.get(c["trace_id"]) in fail_blinds]
    selected = {c["trace_id"] for c in chosen}
    never = [c for c in candidates if c["trace_id"] not in selected]
    unlabeled = never + [c for c in chosen if c["trace_id"] in blanks]
    fail_scenarios = Counter(mapping[c["task_id"]] for c in fails)
    unlabeled_scenarios = {mapping[c["task_id"]] for c in unlabeled}
    return {
        "status": "provisional",
        "candidates": len(candidates),
        "candidate_tasks": len({c["task_id"] for c in candidates}),
        "candidate_scenarios": len({mapping[c["task_id"]] for c in candidates}),
        "selected": len(chosen),
        "labeled": len(labeled),
        "blank_in_selected": sorted(blank_blinds),
        "never_selected": len(never),
        "unlabeled_total": len(unlabeled),
        "human_fail": {
            "n_traj": len(fails),
            "n_scenario": len(fail_scenarios),
            "per_scenario": [{"scenario_id": s, "fail_traces": n} for s, n in sorted(fail_scenarios.items())],
            "trace_ids": sorted(c["trace_id"] for c in fails),
        },
        "gate_b": {"required_scenarios": GATE_B_SCENARIOS, "n_scenario": len(fail_scenarios),
                   "triggered": len(fail_scenarios) < GATE_B_SCENARIOS},
        "unlabeled_pool": {
            "n_traj": len(unlabeled),
            "n_scenario": len(unlabeled_scenarios),
            "scenarios_new_to_fail_pool": len(unlabeled_scenarios - set(fail_scenarios)),
            "trace_ids": sorted(c["trace_id"] for c in unlabeled),
        },
    }


def write_blind_batch(trace_ids: Sequence[str], csv_path: Path, key_path: Path) -> dict[str, Any]:
    """Standby roster for gate B: blank rows and fresh blind ids, never a label."""
    if csv_path.exists() or key_path.exists():
        raise SystemExit("batch_extra CSV or key already exists; refusing to overwrite")
    mapping = kit.blind_ids(sorted(trace_ids), seed=kit.new_seed())
    kit.write_template(csv_path, sorted(mapping.values()))
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(mapping, indent=1), encoding="utf-8")
    return {"rows": len(mapping), "csv": str(csv_path), "key": str(key_path),
            "views_rendered": False,
            "note": f"仅预分配 {len(mapping)} 个盲 ID 与空白行；未渲染视图，也未冻结这些轨迹的证据哈希"}


def dry_run_section(plan_path: Path, published: Path, replay: Path | None) -> dict[str, Any]:
    """Cost plan plus the cache-coverage evidence; a peak estimate is not an invoice."""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out = {"plan": plan, "new_api_calls": 0, "new_cost_usd": 0.0,
           "basis": "offline replay refuses cache misses; usage-log cost unchanged"}
    if replay is None or not replay.is_file():
        out["replay"] = None
        return out
    a = {r["job_id"]: r for r in latest_rows(load_rows(published))}
    b = {r["job_id"]: r for r in latest_rows(load_rows(replay))}
    same = set(a) == set(b)
    diffs = [k for k in a if k in b and (a[k].get("score"), a[k].get("status"), a[k].get("reason"))
             != (b[k].get("score"), b[k].get("status"), b[k].get("reason"))]
    out["replay"] = {
        "published_rows": len(a), "replay_rows": len(b), "same_job_set": same,
        "score_status_reason_differences": len(diffs),
        "error_rows_published": sum(r.get("status") != "ok" for r in a.values()),
        "error_rows_replay": sum(r.get("status") != "ok" for r in b.values()),
        "error_reasons_replay": dict(Counter(str(r.get("reason")) for r in b.values() if r.get("status") != "ok")),
        "error_rows_by_arm": {
            "defended": sum(r.get("status") != "ok" and r.get("defended") for r in b.values()),
            "undefended": sum(r.get("status") != "ok" and not r.get("defended") for r in b.values()),
        },
        "rows_by_arm": {
            "defended": sum(bool(r.get("defended")) for r in b.values()),
            "undefended": sum(not r.get("defended") for r in b.values()),
        },
        "cache_misses": sum("cache miss" in str(r.get("reason") or "") for r in b.values()),
        "identical": same and not diffs,
    }
    return out


def baseline_fail_summary(pairs: Sequence[Mapping[str, Any]], clusters: Mapping[str, str]) -> dict[str, Any]:
    """§6 third metric: fail→pass among baseline-fail, denominator n_traj, counts only."""
    out: dict[str, Any] = {}
    for grader in sorted({p["grader"] for p in pairs}):
        for defended in (False, True):
            subset = [p for p in pairs if p["grader"] == grader and p["defended"] == defended and p["base_fail"]]
            traces = sorted({p["trace_id"] for p in subset})
            scenarios = sorted({clusters[t] for t in traces})
            flipped = sorted({p["trace_id"] for p in subset if p["fail_to_pass"]})
            out[f"{grader}|{'def' if defended else 'raw'}"] = {
                "n_traj": len(traces), "n_scenario": len(scenarios), "pairs": len(subset),
                "fail_to_pass_traj": len(flipped), "case_study": len(scenarios) < ss.MIN_SCENARIOS,
                "fail_to_pass_pairs": sum(p["fail_to_pass"] for p in subset),
                "pass_to_fail_pairs": sum(p["pass_to_fail"] for p in subset),
                "trace_ids": traces, "fail_to_pass_trace_ids": flipped, "scenario_ids": scenarios,
            }
    return out


def injection_analysis(rows: Sequence[Mapping[str, Any]], mapping: Mapping[str, str], *,
                       resamples: int, seed: int) -> dict[str, Any]:
    """Scenario-level flips per (grader, variant, arm) and the 16-test undefended Holm family."""
    pairs, unpaired = ss.paired_observations(rows)
    clusters = {r["trace_id"]: mapping[r["task_id"]] for r in rows if "task_id" in r}
    if not clusters:
        raise ValueError("rows carry no task_id; scenario clustering is impossible")
    units = []
    family: dict[str, float | None] = {}
    descriptive: dict[str, Any] = {}
    for (grader, variant, defended), group in sorted(ss.cells(pairs).items()):
        aggregates = ss.scenario_aggregates(group, clusters)
        rates = ss.scenario_rates(aggregates, resamples=resamples, seed=seed)
        test = ss.sign_flip_test([a["mean_delta"] for a in aggregates], seed=seed)
        name = f"{grader}|{variant}"
        entry = {"grader": grader, "variant": variant, "defended": defended,
                 "paired_observations": len(group), "rates": rates,
                 "sign_flip": test, "per_scenario": ss.scenario_table(aggregates)}
        units.append(entry)
        if defended:
            descriptive[name] = test
        else:
            family[name] = test["p"] if rates["n_scenario"] >= ss.MIN_SCENARIOS else None
    return {
        "status": "provisional",
        "unpaired_observations": unpaired,
        "units": units,
        "baseline_fail": baseline_fail_summary(pairs, clusters),
        "confirmatory_family": ss.holm(family),
        "defended_arm_descriptive": descriptive,
    }


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _ci(interval: Mapping[str, Any]) -> str:
    if interval.get("ci") is not None:
        lo, hi = interval["ci"]
        return f"[{lo:.4f}, {hi:.4f}]"
    if interval.get("status") == "unreliable":
        return f"不可靠（undefined {interval.get('undefined_share', 0):.2f}）"
    if interval.get("resamples") and interval.get("defined_draws") == interval["resamples"]:
        return "不可估（零宽：场景指标全 0 或全 1）"
    return f"不可估（{interval.get('status')}）"


def _escape(text: Any) -> str:
    """Test names contain '|', which would otherwise split a markdown table cell."""
    return str(text).replace("|", "\\|")


def markdown(pool: Mapping[str, Any], analyses: Mapping[str, Any], dry: Mapping[str, Any],
             batch: Mapping[str, Any] | None) -> str:
    lines = [
        "# Phase 3 — PROVISIONAL（不得写入 FINAL_REPORT_v2 / RESUME_CLAIMS）",
        "",
        "**状态：PROVISIONAL。** 依赖 round1 人工标签，闸门 A 未通过，人类 test-retest κ 未知。",
        "依据 `docs/PREREG_v2.md` §6 / §6b。若 κ < 0.60，本文件全部结果永久降级为 exploratory。",
        "",
        "## 1. 候选池与场景去重",
        "",
        "| 口径 | merge（主） | split（敏感性） |",
        "| --- | --- | --- |",
    ]
    merge, split = pool["merge"], pool["split"]
    rows = [
        ("完成轨迹候选", "candidates"), ("distinct task_id", "candidate_tasks"),
        ("distinct scenario_id", "candidate_scenarios"), ("已选入标注", "selected"),
        ("已标注", "labeled"), ("从未选入", "never_selected"), ("未标注合计", "unlabeled_total"),
    ]
    for label, field in rows:
        lines.append(f"| {label} | {merge[field]} | {split[field]} |")
    lines += [
        f"| 人工 fail 轨迹 | {merge['human_fail']['n_traj']} | {split['human_fail']['n_traj']} |",
        f"| 人工 fail 独立场景 | {merge['human_fail']['n_scenario']} | {split['human_fail']['n_scenario']} |",
        f"| 闸门 B（需 ≥{GATE_B_SCENARIOS} 场景） | "
        f"{'触发' if merge['gate_b']['triggered'] else '不触发'} | "
        f"{'触发' if split['gate_b']['triggered'] else '不触发'} |",
    ]
    triggered = [name for name in ("merge", "split") if pool[name]["gate_b"]["triggered"]]
    gate_line = (
        f"- **闸门 B 触发（{', '.join(triggered)}）**：人工 fail 池独立场景 < {GATE_B_SCENARIOS}，"
        "需要 owner 盲标 `annotation/batch_extra.csv` 后才能扩展注入实验。"
        if triggered else
        f"- **闸门 B 在两种口径下都不触发**：人工 fail 池已覆盖 ≥{GATE_B_SCENARIOS} 个独立场景，不需要新增标注。")
    same_pool = (merge["human_fail"]["trace_ids"] == split["human_fail"]["trace_ids"]
                 and merge["human_fail"]["n_scenario"] == split["human_fail"]["n_scenario"])
    lines += [
        f"- 空白行：{merge['blank_in_selected']}（未标注，未排除）。",
        f"- 未标注池覆盖 {merge['unlabeled_pool']['n_scenario']} 个场景，其中 "
        f"{merge['unlabeled_pool']['scenarios_new_to_fail_pool']} 个不在人工 fail 池内。",
        gate_line,
        f"- T159zh/T160 归并歧义（owner 待核对）：全库场景数 merge {merge['candidate_scenarios']} / "
        f"split {split['candidate_scenarios']}；**对 Phase 3 候选池{'无影响' if same_pool else '有影响'}**"
        f"（人工 fail 池 merge {merge['human_fail']['n_traj']} 轨迹 / {merge['human_fail']['n_scenario']} 场景，"
        f"split {split['human_fail']['n_traj']} / {split['human_fail']['n_scenario']}）。",
        "",
        "### 人工 fail 池按场景（merge）",
        "",
        "| scenario_id | fail 轨迹数 |",
        "| --- | --- |",
    ]
    lines += [f"| {r['scenario_id']} | {r['fail_traces']} |" for r in merge["human_fail"]["per_scenario"]]
    lines += ["", "## 2. Dry-run 成本与缓存覆盖", ""]
    plan, replay = dry["plan"], dry["replay"]
    estimate = plan["peak_cap_based_estimate_usd"]
    lines += [
        f"- 逻辑 job **{plan['jobs']}**，completions **{plan['completions']}**，"
        f"峰值上限估算 **${estimate}**（字符估算，非账单）。",
        f"- **新增 API 调用 {dry['new_api_calls']}，新增花费 ${dry['new_cost_usd']:.2f}**（{dry['basis']}）。",
    ]
    if replay is None:
        lines.append("- 离线 replay：未提供，缓存覆盖**未验证**。")
    else:
        lines += [
            f"- 离线 replay：{replay['replay_rows']}/{replay['published_rows']} 行，job 集合一致 "
            f"{replay['same_job_set']}，score/status/reason 差异 **{replay['score_status_reason_differences']}**。",
            f"- 缓存未命中 **{replay['cache_misses']}**（`--offline` 下任何未命中都会报错，故 0 即全覆盖）。",
            f"- error 行 **{replay['error_rows_published']}**（replay {replay['error_rows_replay']}），"
            f"按臂：防御 {replay['error_rows_by_arm']['defended']} / 未防御 {replay['error_rows_by_arm']['undefended']}；"
            "如实保留，不补全。",
        ]
        lines += [f"  - `{_escape(reason)}` × {count}"
                  for reason, count in sorted(replay["error_reasons_replay"].items(), key=lambda kv: -kv[1])]
    if estimate > 5:
        lines.append(f"- ⚠️ 峰值估算 ${estimate} **超过 $5 硬上限**：若缓存失效需要真实重跑，"
                     "必须先停下询问 owner，不得直接跑。")
    lines += ["", "## 3. 闸门 B 盲标批次（备用）", ""]
    if batch:
        lines += [f"- 已预分配 {batch['rows']} 个盲 ID 与空白行：`{_escape(batch['csv'])}`。",
                  f"- 私钥：`{_escape(batch['key'])}`（不在 annotation/ 内）。",
                  f"- {batch['note']}。"]
    else:
        lines.append("- 已存在或显式跳过，未覆盖。")
    lines += ["", "## 4. 注入结果（PROVISIONAL）", "",
              "§6 主指标 **ASR 按配对计**（分母 = 全部有效配对），§6b 主结果 **按场景计**",
              "（`asr_flip` = 场景内配对差均值 > 0；`verdict_flip` = 场景内至少一个判定变化）。",
              "两者分开报告，不合并成一个数。**未防御臂（raw）**为 confirmatory 族，防御臂（def）仅描述性。", ""]
    for variant_name, analysis in analyses.items():
        family = analysis["confirmatory_family"]
        lines += [f"### 口径：{variant_name}", "", "#### 4.1 配对级（§6 主指标 ASR）", "",
                  "| grader | variant | 臂 | n_traj | n_scenario | 有效配对 | ASR 分子 | ASR | fail→pass | pass→fail | 判定变化 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for unit in analysis["units"]:
            rates, pair = unit["rates"], unit["rates"]["pair_level"]
            arm = "def" if unit["defended"] else "raw"
            lines.append(
                f"| {_escape(unit['grader'].replace('trajectory_', ''))} | {_escape(unit['variant'])} | {arm} "
                f"| {rates['n_traj']} | {rates['n_scenario']} | {rates['pairs']} "
                f"| {pair['positive']} | {_fmt(pair['asr'])} | {pair['fail_to_pass']} | {pair['pass_to_fail']} "
                f"| {pair['verdict_changed']} |")
        lines += ["", "#### 4.2 场景级（§6b 主结果）", "",
                  "| grader | variant | 臂 | 场景数 | 非零均值场景 | asr_flip | ASR 率 [95% CI] "
                  "| verdict_flip | 翻转率 [95% CI] | sign-flip p | Holm p_adj |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for unit in analysis["units"]:
            rates = unit["rates"]
            arm = "def" if unit["defended"] else "raw"
            counts = rates["counts"]
            name = f"{unit['grader']}|{unit['variant']}"
            adjusted = family["tests"].get(name, {}).get("p_adjusted") if not unit["defended"] else None
            lines.append(
                f"| {_escape(unit['grader'].replace('trajectory_', ''))} | {_escape(unit['variant'])} | {arm} "
                f"| {rates['n_scenario']} | {rates['informative_clusters']} | {counts['asr_flip']} "
                f"| {_fmt(rates['rates']['asr_flip'])} {_ci(rates['intervals']['asr_flip'])} "
                f"| {counts['verdict_flip']} | {_fmt(rates['rates']['verdict_flip'])} "
                f"{_ci(rates['intervals']['verdict_flip'])} | {_fmt(unit['sign_flip']['p'])} "
                f"| {_fmt(adjusted, 6) if adjusted is not None else '—（族外）'} |")
        lines += ["", f"**Holm 族**：{family['family_size']} 个检验，α={family['alpha']}，"
                  f"拒绝 {len(family['rejected'])} 个；跳过（场景数不足）{len(family['skipped'])} 个。", ""]
        if family["rejected"]:
            lines += ["| 检验 | p | p_adjusted |", "| --- | --- | --- |"]
            lines += [f"| {_escape(name)} | {_fmt(family['tests'][name]['p'], 6)} "
                      f"| {_fmt(family['tests'][name]['p_adjusted'], 6)} |" for name in family["rejected"]]
            lines.append("")
        if family["skipped"]:
            lines += [f"- 跳过（只报描述性）：{_escape(', '.join(family['skipped']))}", ""]
        lines += [f"- 未配对观测：{analysis['unpaired_observations']}（invalid/缺基线，如实保留，不补全）。", "",
                  "#### 4.3 per-scenario × per-variant 翻转表（未防御臂，计数）", "",
                  "单元格 = `asr_flip/verdict_flip`（0 或 1）；`—` = 该场景在该变体下无有效配对。",
                  "各场景的 `mean_delta`、配对数与方向计数见 `reports/phase3_scenario.json` → `units[].per_scenario`。", ""]
        for grader in sorted({u["grader"] for u in analysis["units"] if not u["defended"]}):
            units = [u for u in analysis["units"] if u["grader"] == grader and not u["defended"]]
            variants = sorted(u["variant"] for u in units)
            lookup = {(u["variant"], row["scenario_id"]): row for u in units for row in u["per_scenario"]}
            scenarios = sorted({key[1] for key in lookup})
            lines += [f"**{_escape(grader)}**", "",
                      "| scenario | " + " | ".join(_escape(v) for v in variants) + " |",
                      "| --- |" + " --- |" * len(variants)]
            for scenario in scenarios:
                cells = []
                for variant in variants:
                    row = lookup.get((variant, scenario))
                    cells.append("—" if row is None else f"{int(row['asr_flip'])}/{int(row['verdict_flip'])}")
                lines.append(f"| {_escape(scenario)} | " + " | ".join(cells) + " |")
            lines.append("")
        lines += ["#### 4.4 fail→pass among baseline-fail（§6 第三指标，仅为与 v1 可比）", "",
                  "| grader | 臂 | baseline-fail n_traj | n_scenario | 配对 | fail→pass 轨迹 | fail→pass 配对 | 口径 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for name, entry in sorted(analysis["baseline_fail"].items()):
            grader, arm = name.split("|")
            lines.append(
                f"| {_escape(grader.replace('trajectory_', ''))} | {arm} | {entry['n_traj']} | {entry['n_scenario']} "
                f"| {entry['pairs']} | {entry['fail_to_pass_traj']} | {entry['fail_to_pass_pairs']} "
                f"| {'case study（不出百分比）' if entry['case_study'] else '可报率'} |")
        lines.append("")
        for name, entry in sorted(analysis["baseline_fail"].items()):
            if not (entry["case_study"] and entry["n_traj"] and entry["pairs"]):
                continue
            ratio = entry["fail_to_pass_pairs"] / entry["pairs"]
            v1 = "；**v1 报告的「75% 翻转率」正是这个比值**" if abs(ratio - 0.75) < 1e-9 else ""
            lines.append(
                f"- {_escape(name)} 的旧口径分解：{entry['fail_to_pass_pairs']}/{entry['pairs']} 配对 = {ratio:.2f}，"
                f"但全部来自 {entry['n_traj']} 条轨迹 / {entry['n_scenario']} 个场景"
                f"（{', '.join(entry['scenario_ids'])}；trace {', '.join(t[:8] for t in entry['trace_ids'])}）"
                f"——8 变体 × 3 重复的伪重复，**不能当作总体翻转率**{v1}。")
        lines.append("")
    lines += ["## 5. 限制（真实的，不是套话）", ""]
    lines += _limitations(pool, analyses, dry)
    lines += [
        "",
        "## 6. 复现",
        "",
        "```bash",
        "python scripts/experiment.py p4 --expected-unlabeled 2 --model deepseek-flash \\",
        "    --thinking off --repeats 3 --run-id p4-phase3-dryrun          # 成本计划，零网络",
        "python scripts/experiment.py p4 --offline --expected-unlabeled 2 --model deepseek-flash \\",
        "    --thinking off --repeats 3 --workers 8 --run-id p4-phase3-replay-check",
        "python scripts/phase3_analysis.py",
        "```",
        "",
    ]
    return "\n".join(lines)


def _limitations(pool: Mapping[str, Any], analyses: Mapping[str, Any], dry: Mapping[str, Any]) -> list[str]:
    """Every numeric limitation is read back from the computed results, never typed in."""
    primary = analyses[pool.get("primary_variant", "merge")]
    out = ["- 单模型（deepseek-flash）、judge think=off、4 个英文模板；跨 vendor 与跨语言未测（闸门 C）。"]
    for name, entry in sorted(primary["baseline_fail"].items()):
        if entry["n_traj"]:
            out.append(f"- baseline-fail 子集（{_escape(name)}）只有 {entry['n_traj']} 条轨迹 / "
                       f"{entry['n_scenario']} 个场景 → `fail→pass among baseline-fail` 是 case study，不出百分比结论句。")
    saturated = [name for name, entry in primary["baseline_fail"].items()
                 if entry["n_traj"] == 0 and name.endswith("|raw")]
    if saturated:
        out.append(f"- {_escape(', '.join(saturated))} 的未扰动基线无一低于阈值（饱和），"
                   "其 verdict flip 只能来自 pass→fail 方向；ASR 因此比翻转率更有信息量。")
    for grader in sorted({u["grader"] for u in primary["units"] if not u["defended"]}):
        cells = [u for u in primary["units"] if u["grader"] == grader and not u["defended"]]
        info = [u["rates"]["informative_clusters"] for u in cells]
        ks = {u["sign_flip"]["k"] for u in cells}
        if min(info) < min(ks):
            out.append(f"- {_escape(grader)}：sign-flip 的 k={sorted(ks)}，但非零均值场景只有 "
                       f"{min(info)}–{max(info)} 个；其余场景配对差均值为 0，在置换下不变，"
                       "**p 值实际由这几个场景支撑**，证据厚度远低于 k 的表面值。")
    replay = dry.get("replay")
    if replay:
        arms, rows = replay["error_rows_by_arm"], replay["rows_by_arm"]
        out.append(f"- 防御臂格式失败 {arms['defended']}/{rows['defended']} vs 未防御 "
                   f"{arms['undefended']}/{rows['undefended']}：防御收益与「缺失非随机」假设纠缠，"
                   "见 Phase 1 敏感性分析；本轮不据此下防御结论。")
    out.append("- 本文件全部数字依赖 round1 标签；人类 test-retest κ 未测（闸门 A 未过），"
               "因此**没有任何结论可以升级为 confirmatory**。")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--injection", type=Path, default=root / "outputs/p4/p4-flash-human-fail-16.jsonl")
    parser.add_argument("--replay", type=Path, default=root / "outputs/p4/p4-phase3-replay-check.jsonl")
    parser.add_argument("--plan", type=Path, default=root / "reports/phase3_dryrun_plan.json")
    parser.add_argument("--scenario-map", type=Path, default=root / "reports/scenario_map.csv")
    parser.add_argument("--uncertain", type=Path, default=root / "reports/scenario_map_uncertain.json")
    parser.add_argument("--resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--batch-csv", type=Path, default=root / "annotation/batch_extra.csv")
    parser.add_argument("--batch-key", type=Path, default=root / "outputs/annotation/batch_extra_key.json")
    parser.add_argument("--no-batch", action="store_true", help="skip the standby gate-B roster")
    args = parser.parse_args()

    variants = scenario_variants(args.scenario_map, args.uncertain)
    meta = json.loads((root / "outputs/p2/annotation_meta.json").read_text(encoding="utf-8"))
    key = json.loads((root / "outputs/annotation/key.json").read_text(encoding="utf-8"))
    labels = kit.read_labels(root / "annotation/labels.csv")
    pool = {name: pool_stats(meta["all_candidates"], meta["chosen"], labels, key, variants[name])
            for name in ("merge", "split")}
    pool["scenario_variant_flagged"] = variants["flagged"]
    pool["primary_variant"] = "merge"

    rows = latest_rows(load_rows(args.injection))
    tasks = {r["trace_id"]: r["task_id"] for r in meta["chosen"]}
    for row in rows:
        row["task_id"] = tasks[row["trace_id"]]
    analyses = {name: injection_analysis(rows, variants[name], resamples=args.resamples, seed=args.seed)
                for name in ("merge", "split")}
    dry = dry_run_section(args.plan, args.injection, args.replay)
    batch = None
    if not args.no_batch:
        if args.batch_csv.exists() or args.batch_key.exists():
            print("batch_extra already exists; refusing to overwrite", file=sys.stderr)
            if args.batch_csv.exists() and args.batch_key.exists():
                existing = kit.read_labels(args.batch_csv)
                batch = {"rows": len(existing), "csv": str(args.batch_csv), "key": str(args.batch_key),
                         "views_rendered": False, "reused": True,
                         "note": f"已存在 {len(existing)} 行空白盲标行，本次未覆盖；未渲染视图，也未冻结证据哈希"}
        else:
            batch = write_blind_batch(pool["merge"]["unlabeled_pool"]["trace_ids"], args.batch_csv, args.batch_key)

    atomic_text(root / "reports/phase3_pool.json", json.dumps(pool, ensure_ascii=False, indent=1) + "\n")
    atomic_text(root / "reports/phase3_scenario.json",
                json.dumps({"status": "provisional", "dry_run": dry, "batch": batch, "analyses": analyses},
                           ensure_ascii=False, indent=1) + "\n")
    atomic_text(root / "reports/phase3_provisional.md", markdown(pool, analyses, dry, batch))
    for name in ("merge", "split"):
        fail = pool[name]["human_fail"]
        print(f"[PROVISIONAL] {name}: 人工 fail {fail['n_traj']} 轨迹 / {fail['n_scenario']} 场景；"
              f"闸门 B {'触发' if pool[name]['gate_b']['triggered'] else '不触发'}")
    print(f"[PROVISIONAL] dry-run: {dry['plan']['jobs']} jobs, 峰值估算 ${dry['plan']['peak_cap_based_estimate_usd']}, "
          f"新增花费 $0.00, replay identical={dry['replay']['identical'] if dry['replay'] else 'n/a'}")
    for name, analysis in analyses.items():
        family = analysis["confirmatory_family"]
        print(f"[PROVISIONAL] {name}: Holm 族 {family['family_size']}，拒绝 {len(family['rejected'])}，"
              f"跳过 {len(family['skipped'])}")
    print("written: reports/phase3_pool.json, reports/phase3_scenario.json, reports/phase3_provisional.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())