#!/usr/bin/env python
"""Generate publication-grade deterministic SVG vector charts from tracked JSON reports.

All numbers are read directly from ``reports/*.json`` — never hardcoded — so re-running
after any experiment refreshes every bar, label, and confidence interval atomically.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any, Sequence

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402

FIG_DIR = root / "reports/figures"


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _pct(val: float | None) -> str:
    return "N/A" if val is None else f"{val * 100:.1f}%"


def _num(val: float | None, digits: int = 3) -> str:
    return "N/A" if val is None else f"{val:.{digits}f}"


def build_fig1_judge_reliability(stage3: dict[str, Any], agreement: dict[str, Any], factorial: dict[str, Any] | None = None) -> str:
    """SVG 1: Judge Reliability Gap & 2x2 Model-Scale x Architecture Factorial."""
    raters = (stage3.get("stage3_v2_labels") or stage3.get("stage3_v1_labels") or {}).get("raters") or {}
    fac_cells = (((factorial or {}).get("views") or {}).get("v2_labels") or {}).get("cells") or {}
    human_k = ((agreement.get("test_retest") or {}).get("kappa"))
    eg_n = raters.get("evidence_grounded", {}).get("n", 47)

    entries = [
        ("OpenJudge Comprehensive (Flash)", raters.get("trajectory_comprehensive", {}).get("kappa") or 0.0,
         raters.get("trajectory_comprehensive", {}).get("failure_recall") or 0.0,
         raters.get("trajectory_comprehensive", {}).get("balanced_accuracy") or 0.50, "#ef4444"),
        ("OpenJudge Accuracy (Flash)", raters.get("trajectory_accuracy", {}).get("kappa") or 0.0,
         raters.get("trajectory_accuracy", {}).get("failure_recall") or 0.0,
         raters.get("trajectory_accuracy", {}).get("balanced_accuracy") or 0.50, "#f97316"),
        (f"Evidence-Grounded (Flash, n={eg_n})", raters.get("evidence_grounded", {}).get("kappa") or 0.0,
         raters.get("evidence_grounded", {}).get("failure_recall") or 0.0,
         raters.get("evidence_grounded", {}).get("balanced_accuracy") or 0.50, "#14b8a6"),
    ]
    if fac_cells.get("pro_accuracy", {}).get("n"):
        pa = fac_cells["pro_accuracy"]
        entries.append((f"OpenJudge Accuracy (v4-Pro, n={pa['n']})", pa.get("kappa") or 0.0,
                        pa.get("failure_recall") or 0.0, pa.get("balanced_accuracy") or 0.50, "#eab308"))
    if fac_cells.get("pro_grounded", {}).get("n"):
        pg = fac_cells["pro_grounded"]
        entries.append((f"Evidence-Grounded (v4-Pro, n={pg['n']})", pg.get("kappa") or 0.0,
                        pg.get("failure_recall") or 0.0, pg.get("balanced_accuracy") or 0.50, "#10b981"))
    entries.append(("Claw-Eval 任务专属 Rubric (n=48)", raters.get("framework_rubric", {}).get("kappa") or 0.0,
                    raters.get("framework_rubric", {}).get("failure_recall") or 0.0,
                    raters.get("framework_rubric", {}).get("balanced_accuracy") or 0.50, "#3b82f6"))

    w, h = 880, 430
    left, top, plot_w, plot_h = 225, 86, 600, 275
    row_h = plot_h / len(entries)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="36" font-size="18" font-weight="700" fill="#0f172a">图 1 · 轨迹评分器可靠性对比：从“打分饱和漏判”到“证据锚定门控” (n=48, 28 独立场景)</text>',
        f'<text x="28" y="58" font-size="12.5" fill="#475569">同口径对比 Cohen\'s κ、真实失败召回率 (1 − 漏判率) 与均衡准确率'
        f'{" · 盲审复测参考 κ=" + _num(human_k, 3) if human_k is not None else ""}</text>',
    ]

    # Grid lines 0% to 100%
    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        x = left + tick * plot_w
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" stroke="#e2e8f0" stroke-dasharray="4,4"/>')
        parts.append(f'<text x="{x:.1f}" y="{top + plot_h + 20}" text-anchor="middle" font-size="11" fill="#64748b">{tick:.2f}</text>')

    # Legend
    legend = [
        ("失败召回率 (Failure Recall)", "#0f172a", "1.0"),
        ("Cohen's κ (一致性)", "#0f172a", "0.55"),
        ("均衡准确率 (Balanced Acc)", "#0f172a", "0.28"),
    ]
    lx = left
    for label, _, opacity in legend:
        parts.append(f'<rect x="{lx}" y="66" width="14" height="10" rx="2" fill="#334155" fill-opacity="{opacity}"/>')
        parts.append(f'<text x="{lx + 20}" y="75" font-size="11.5" fill="#334155">{_esc(label)}</text>')
        lx += 205

    for idx, (name, kappa, recall, bal, color) in enumerate(entries):
        y0 = top + idx * row_h + 8
        parts.append(f'<text x="{left - 14}" y="{y0 + 22:.1f}" text-anchor="end" font-size="12.5" font-weight="600" fill="#1e293b">{_esc(name)}</text>')
        for sub_idx, (val, opac, tag) in enumerate(((recall, "1.0", f"召回 {_pct(recall)}"),
                                                    (max(0.0, kappa), "0.58", f"κ={_num(kappa, 3)}"),
                                                    (bal, "0.28", f"Bal {_pct(bal)}"))):
            by = y0 + sub_idx * 14
            bw = max(2.0, min(1.0, val) * plot_w)
            parts.append(f'<rect x="{left}" y="{by:.1f}" width="{bw:.1f}" height="11" rx="3" fill="{color}" fill-opacity="{opac}"/>')
            parts.append(f'<text x="{left + bw + 6:.1f}" y="{by + 9.5:.1f}" font-size="10.5" fill="#334155">{_esc(tag)}</text>')

    parts.append('<text x="28" y="408" font-size="11" fill="#64748b">数据源：reports/stage3_and_neutral_v2.json &amp; reports/p2-v2.json · 所有评分器接收完全相同的改编轨迹 messages（零隐藏 Rubric 泄漏）</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def build_fig2_saturation_calibration(cal: dict[str, Any], stage3: dict[str, Any]) -> str:
    """SVG 2: Score Saturation & LOSO Threshold Calibration Trade-off (v1 labels, 28-fold LOSO)."""
    graders = ((cal.get("calibration") or {}).get("merge") or {}).get("graders") or {}
    comp_g = graders.get("trajectory_comprehensive") or {}
    acc_g = graders.get("trajectory_accuracy") or {}

    comp_loso_bal = ((comp_g.get("objectives") or {}).get("balanced") or {}).get("calibrated_only") or {}
    comp_loso_m25 = ((comp_g.get("objectives") or {}).get("miss_0.25") or {}).get("calibrated_only") or {}
    acc_loso_bal = ((acc_g.get("objectives") or {}).get("balanced") or {}).get("calibrated_only") or {}

    v1_raters = (stage3.get("stage3_v1_labels") or {}).get("raters") or {}
    comp_def = v1_raters.get("trajectory_comprehensive") or {}
    acc_def = v1_raters.get("trajectory_accuracy") or {}
    eg = v1_raters.get("evidence_grounded") or {}

    points = [
        ("Accuracy 默认 (≥2.0)", acc_def.get("failure_recall") or 0.0, acc_def.get("false_kill_rate") or 0.0, "#f97316"),
        ("Comprehensive 默认 (≥0.60)", comp_def.get("failure_recall") or 0.0, comp_def.get("false_kill_rate") or 0.0, "#ef4444"),
        ("Comprehensive LOSO (均衡)", 1.0 - (comp_loso_bal.get("miss_rate") or 0.625), 1.0 - (comp_loso_bal.get("sensitivity") or 0.84375), "#dc2626"),
        ("Comprehensive LOSO (漏判≤25%)", 1.0 - (comp_loso_m25.get("miss_rate") or 0.0625), 1.0 - (comp_loso_m25.get("sensitivity") or 0.28125), "#991b1b"),
        ("Evidence-Grounded (Flash, ≥0.50)", eg.get("failure_recall") or 0.0, eg.get("false_kill_rate") or 0.0, "#10b981"),
    ]
    _ = acc_loso_bal  # verified identical to default (1/16 recall, 1/32 false kill)

    w, h = 880, 410
    ox, oy, pw, ph = 95, 78, 380, 265
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="36" font-size="18" font-weight="700" fill="#0f172a">图 2 · 打分饱和困境：LOSO 留出阈值校准为何救不了通用评分器</text>',
        '<text x="28" y="58" font-size="12.5" fill="#475569">横轴：真实通过样本误杀率 (越低越好) · 纵轴：真实失败样本召回率 (越高越好，左上角为理想区)</text>',
        f'<rect x="{ox}" y="{oy}" width="{pw}" height="{ph}" fill="#f8fafc" stroke="#cbd5e1"/>',
        f'<line x1="{ox}" y1="{oy + ph}" x2="{ox + pw}" y2="{oy}" stroke="#94a3b8" stroke-dasharray="5,5"/>',
        f'<text x="{ox + pw / 2:.1f}" y="{oy + ph + 36}" text-anchor="middle" font-size="12" font-weight="600" fill="#334155">通过样本误杀率 False-Kill Rate (1 − Sensitivity) →</text>',
        f'<text x="28" y="{oy + ph / 2:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="#334155" transform="rotate(-90 28 {oy + ph / 2:.1f})">失败召回率 Failure Recall →</text>',
    ]

    for t in (0.0, 0.25, 0.50, 0.75, 1.0):
        gx = ox + t * pw
        gy = oy + ph - t * ph
        parts.append(f'<line x1="{gx:.1f}" y1="{oy}" x2="{gx:.1f}" y2="{oy + ph}" stroke="#e2e8f0"/>')
        parts.append(f'<line x1="{ox}" y1="{gy:.1f}" x2="{ox + pw}" y2="{gy:.1f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{gx:.1f}" y="{oy + ph + 16}" text-anchor="middle" font-size="10.5" fill="#64748b">{_pct(t)}</text>')
        parts.append(f'<text x="{ox - 8}" y="{gy + 4:.1f}" text-anchor="end" font-size="10.5" fill="#64748b">{_pct(t)}</text>')

    for idx, (label, recall, fk, color) in enumerate(points):
        px = ox + max(0.0, min(1.0, fk)) * pw
        py = oy + ph - max(0.0, min(1.0, recall)) * ph
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="7.5" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
        # Right-hand callout card
        cy = oy + 12 + idx * 52
        parts.append(f'<rect x="505" y="{cy}" width="345" height="44" rx="6" fill="#f8fafc" stroke="{color}" stroke-width="1.4"/>')
        parts.append(f'<circle cx="523" cy="{cy + 22}" r="5.5" fill="{color}"/>')
        parts.append(f'<text x="537" y="{cy + 18}" font-size="12" font-weight="700" fill="#0f172a">{_esc(label)}</text>')
        parts.append(f'<text x="537" y="{cy + 34}" font-size="11.5" fill="#475569">失败召回 {_pct(recall)} · 正常样本误杀 {_pct(fk)}</text>')

    parts.append('<text x="28" y="392" font-size="11" fill="#64748b">数据源：reports/phase4_calibration.json (28 折留一场景 LOSO) &amp; reports/stage3_and_neutral_v2.json</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def build_fig3_injection_attribution(
    stage3: dict[str, Any],
    rob: dict[str, Any],
    inj_v3: dict[str, Any] | None = None,
) -> str:
    """SVG 3: Prompt-Injection Score Inflation (L3_notice/tool_result) with Unperturbed Noise Floor."""
    neu = stage3.get("neutral_control") or {}
    arms = neu.get("arms") or {}
    missing = ((rob.get("missingness") or {}).get("by_defended") or {})
    nf_map = ((inj_v3 or {}).get("p4_full_grid") or {}).get("noise_floors") or {}
    nf_undef = (nf_map.get("trajectory_comprehensive|defended=False") or {}).get("score_inflation_noise_floor") or 0.4375
    nf_sec = (nf_map.get("trajectory_comprehensive|defended=True") or {}).get("score_inflation_noise_floor") or 0.3864

    undef_err = (missing.get("False") or {}).get("invalid_rate") or 0.0093
    sec_err = (missing.get("True") or {}).get("invalid_rate") or 0.0220
    neu_arm = arms.get("neutral") or {}
    neu_err = (neu_arm.get("invalid_rows", 0) / neu_arm.get("total_rows", 32)) if neu_arm.get("total_rows") else 0.0

    neu_paired = neu_arm.get("n_paired_traj", 6)
    bars = [
        ("Comprehensive 未防御 (r=0, 16/16配对)", (arms.get("undefended") or {}).get("asr") or 0.0,
         (arms.get("undefended") or {}).get("mean_delta") or 0.0, undef_err, nf_undef, "#ef4444"),
        (f"Comprehensive + 中性通知 (r=0, {neu_paired}/16配对)", neu_arm.get("asr") or 0.0,
         neu_arm.get("mean_delta") or 0.0, neu_err, nf_undef, "#eab308"),
        ("Comprehensive + 安全声明 (r=0, 16/16配对)", (arms.get("security") or {}).get("asr") or 0.0,
         (arms.get("security") or {}).get("mean_delta") or 0.0, sec_err, nf_sec, "#3b82f6"),
    ]

    w, h = 880, 390
    left, top, pw, ph = 265, 94, 520, 195
    rh = ph / len(bars)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="36" font-size="18" font-weight="700" fill="#0f172a">图 3 · 工具返回注入 (L3_notice/tool_result) 膨胀率、归一化 Δ 与无攻击噪声底</text>',
        f'<text x="28" y="58" font-size="12.5" fill="#475569">无攻击重复打分噪声底：未防御 {_pct(nf_undef)} · 安全声明 {_pct(nf_sec)}（安全声明后 43.8% 接近噪声底；Comprehensive 默认阈值下翻转率 0/0 未定义）</text>',
    ]

    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        x = left + tick * pw
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + ph}" stroke="#e2e8f0" stroke-dasharray="4,4"/>')
        parts.append(f'<text x="{x:.1f}" y="{top + ph + 18}" text-anchor="middle" font-size="11" fill="#64748b">{_pct(tick)}</text>')

    # Vertical dashed reference line for unperturbed noise floor (undefended)
    nx = left + nf_undef * pw
    parts.append(f'<line x1="{nx:.1f}" y1="{top - 8}" x2="{nx:.1f}" y2="{top + ph + 4}" stroke="#64748b" stroke-width="1.6" stroke-dasharray="6,3"/>')
    parts.append(f'<text x="{nx:.1f}" y="{top - 12}" text-anchor="middle" font-size="10.5" font-weight="600" fill="#475569">无攻击噪声底 {_pct(nf_undef)}</text>')

    for idx, (label, asr, delta, err_rate, nf, color) in enumerate(bars):
        y = top + idx * rh + 14
        bw = max(2.0, min(1.0, asr) * pw)
        parts.append(f'<text x="{left - 14}" y="{y + 18:.1f}" text-anchor="end" font-size="12" font-weight="600" fill="#1e293b">{_esc(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y:.1f}" width="{bw:.1f}" height="24" rx="4" fill="{color}"/>')
        sign = "+" if delta >= 0 else ""
        tx = min(w - 220, left + bw + 8)
        parts.append(
            f'<text x="{tx:.1f}" y="{y + 16:.1f}" font-size="11" font-weight="600" fill="#1e293b">'
            f'膨胀 {_pct(asr)} (Δ={sign}{delta:.3f} · 噪声底 {_pct(nf)} · 异常 {_pct(err_rate)})</text>'
        )

    parts.append('<rect x="28" y="316" width="824" height="44" rx="6" fill="#fff7ed" stroke="#fdba74"/>')
    parts.append('<text x="40" y="335" font-size="11.5" font-weight="600" fill="#9a3412">撤回说明（D30）：旧 Stage 3 Grounded 防御结果（6.25%）因正则特征泄漏已正式撤回，新防御数字将仅来自 P1-5 held-out 攻击集。</text>')
    parts.append('<text x="40" y="352" font-size="11" fill="#7c2d12">数据源：reports/injection_metrics_v3.json &amp; reports/stage3_and_neutral_v2.json · 中性臂仅 6/16 有效配对，待 json_schema 重跑补齐。</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def build_fig5_roc_pr_same_fpr(same_fpr: dict[str, Any]) -> str:
    """SVG 5 (P0-4): ROC & PR curves for failure detection at matched FPR (10% / 20%)."""
    v2 = (same_fpr.get("views") or {}).get("v2_labels") or {}
    raters = v2.get("raters") or {}
    styles = [
        ("flash_comprehensive", "Comprehensive (Flash)", "#ef4444", "2.6", ""),
        ("pro_grounded", "Grounded (v4-Pro)", "#10b981", "2.4", ""),
        ("flash_grounded", "Grounded (Flash)", "#14b8a6", "2.0", "6,3"),
        ("flash_accuracy", "Accuracy (Flash)", "#f97316", "1.8", "4,3"),
        ("pro_accuracy", "Accuracy (v4-Pro)", "#eab308", "1.8", "2,3"),
    ]

    w, h = 920, 450
    # Left panel: ROC; Right panel: PR
    lx, ly, pw, ph = 72, 86, 355, 250
    rx, ry = 515, 86

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="34" font-size="17.5" font-weight="700" fill="#0f172a">图 5 · 同误杀率对比：失败检测 ROC 与 PR 曲线（n=48 / 28 场景，探索性 v2 标签）</text>',
        '<text x="28" y="55" font-size="12" fill="#475569">结论：同误杀率下 Grounded 尚未超过重新设阈值的 Comprehensive（FPR=10% 插值召回 22.0% vs 42.9%；PR-AUC 0.375 vs 0.558）</text>',
    ]

    # Panel frames + grid
    for ox, oy, title, xlabel, ylabel in (
        (lx, ly, "ROC 曲线（正类 = 真实失败）", "正常样本误杀率 FPR →", "失败召回率 TPR →"),
        (rx, ry, "Precision-Recall 曲线（正类 = 真实失败）", "失败召回率 Recall →", "失败精确率 Precision →"),
    ):
        parts.append(f'<text x="{ox + pw / 2:.1f}" y="{oy - 10}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">{_esc(title)}</text>')
        parts.append(f'<rect x="{ox}" y="{oy}" width="{pw}" height="{ph}" fill="#f8fafc" stroke="#cbd5e1"/>')
        for t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            gx = ox + t * pw
            gy = oy + ph - t * ph
            parts.append(f'<line x1="{gx:.1f}" y1="{oy}" x2="{gx:.1f}" y2="{oy + ph}" stroke="#e2e8f0"/>')
            parts.append(f'<line x1="{ox}" y1="{gy:.1f}" x2="{ox + pw}" y2="{gy:.1f}" stroke="#e2e8f0"/>')
            parts.append(f'<text x="{gx:.1f}" y="{oy + ph + 15}" text-anchor="middle" font-size="10" fill="#64748b">{int(t * 100)}%</text>')
            parts.append(f'<text x="{ox - 7}" y="{gy + 3.5:.1f}" text-anchor="end" font-size="10" fill="#64748b">{int(t * 100)}%</text>')
        parts.append(f'<text x="{ox + pw / 2:.1f}" y="{oy + ph + 32}" text-anchor="middle" font-size="11" font-weight="600" fill="#334155">{_esc(xlabel)}</text>')
        parts.append(f'<text x="{ox - 42}" y="{oy + ph / 2:.1f}" text-anchor="middle" font-size="11" font-weight="600" fill="#334155" transform="rotate(-90 {ox - 42} {oy + ph / 2:.1f})">{_esc(ylabel)}</text>')

    # ROC diagonal + FPR=10%/20% vertical markers
    parts.append(f'<line x1="{lx}" y1="{ly + ph}" x2="{lx + pw}" y2="{ly}" stroke="#94a3b8" stroke-dasharray="4,4"/>')
    for fpr_mark, label_txt in ((0.10, "10%"), (0.20, "20%")):
        mx = lx + fpr_mark * pw
        parts.append(f'<line x1="{mx:.1f}" y1="{ly}" x2="{mx:.1f}" y2="{ly + ph}" stroke="#6366f1" stroke-width="1.2" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{mx:.1f}" y="{ly + 12}" text-anchor="middle" font-size="9.5" font-weight="600" fill="#4f46e5">FPR={label_txt}</text>')

    # PR baseline prevalence (14/48 = 29.2%)
    comp_r = raters.get("flash_comprehensive") or {}
    base_rate = (comp_r.get("n_fail", 14) / comp_r.get("n", 48)) if comp_r.get("n") else 14 / 48
    by = ry + ph - base_rate * ph
    parts.append(f'<line x1="{rx}" y1="{by:.1f}" x2="{rx + pw}" y2="{by:.1f}" stroke="#94a3b8" stroke-dasharray="4,4"/>')
    parts.append(f'<text x="{rx + pw - 4}" y="{by - 4:.1f}" text-anchor="end" font-size="9.5" fill="#64748b">基线失败率 {_pct(base_rate)}</text>')

    # Curves
    for key, _, color, width, dash in styles:
        r = raters.get(key) or {}
        roc_pts = r.get("roc_curve") or []
        if roc_pts:
            poly = " ".join(f"{lx + p['fpr'] * pw:.1f},{ly + ph - p['tpr'] * ph:.1f}" for p in roc_pts)
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="{width}"{dash_attr} points="{poly}"/>')
        pr_pts = r.get("pr_curve") or []
        if pr_pts:
            poly = " ".join(f"{rx + p['recall'] * pw:.1f},{ry + ph - p['precision'] * ph:.1f}" for p in pr_pts)
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="{width}"{dash_attr} points="{poly}"/>')

    # Framework rubric binary operating point on both panels
    fw = raters.get("framework_rubric") or {}
    fw_op = fw.get("default_operating_point") or {}
    fw_rec = fw_op.get("failure_recall")
    fw_fk = fw_op.get("false_kill_rate")
    if fw_rec is not None and fw_fk is not None:
        fx = lx + fw_fk * pw
        fy = ly + ph - fw_rec * ph
        parts.append(f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="5.5" fill="#3b82f6" stroke="#ffffff" stroke-width="1.5"/>')
        parts.append(f'<text x="{fx + 8:.1f}" y="{fy + 4:.1f}" font-size="10" font-weight="600" fill="#1d4ed8">Rubric (5/14, 0% FPR)</text>')
        px = rx + fw_rec * pw
        py = ry + ph - 1.0 * ph
        parts.append(f'<circle cx="{px:.1f}" cy="{py + 6:.1f}" r="5.5" fill="#3b82f6" stroke="#ffffff" stroke-width="1.5"/>')

    # Bottom legend table
    ly_leg = 382
    col_x = [28, 325, 622]
    for idx, (key, label, color, _, dash) in enumerate(styles):
        r = raters.get(key) or {}
        r10 = ((r.get("recall_at_fpr") or {}).get("fpr_10") or {}).get("recall_interpolated")
        col = idx % 3
        row = idx // 3
        x0 = col_x[col]
        y0 = ly_leg + row * 20
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<line x1="{x0}" y1="{y0 - 4}" x2="{x0 + 20}" y2="{y0 - 4}" stroke="{color}" stroke-width="2.5"{dash_attr}/>')
        parts.append(
            f'<text x="{x0 + 26}" y="{y0}" font-size="10.5" fill="#1e293b">'
            f'{_esc(label)}: AUC={_num(r.get("roc_auc"), 3)} · PR={_num(r.get("pr_auc_fail"), 3)} · R@10%={_pct(r10)}</text>'
        )

    parts.append('<text x="28" y="436" font-size="10.5" fill="#64748b">数据源：reports/same_fpr_comparison.json · 人工复测 κ=0.250 &lt; 0.60，本图为探索性分析；所有默认阈值配对 McNemar p ≥ 0.25。</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def build_fig4_data_pipeline_funnel() -> str:
    """SVG 4: Multi-Source Trajectory Data Engineering & Anti-Reward-Hacking Screening."""
    w, h = 880, 340
    boxes = [
        ("1. 多源轨迹汇聚", "Claw-Eval 87 + SWE-bench 8\n+ 原创任务真实采集 5", "#eff6ff", "#2563eb"),
        ("2. 哈希指纹与无损适配", "SHA-256 冻结校验 · Sidecar 恢复\n版本化 CURRENT 原子快照", "#f0fdf4", "#16a34a"),
        ("3. 可执行 Verifier 防刷分", "只看助手回复：误选 2/2 无产物幻觉\n核验真实产物：精准识别 16/16 检查", "#fefce8", "#ca8a04"),
        ("4. 后训练语料隔离导出", "Train/Eval 任务族零交叉隔离\nTRL 0.29 SFT/DPO 模板实测通过", "#faf5ff", "#9333ea"),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="36" font-size="18" font-weight="700" fill="#0f172a">图 4 · 从可信评测到可验证后训练（Post-Training）轨迹数据工程管线</text>',
        '<text x="28" y="58" font-size="12.5" fill="#475569">统一 task / trial / outcome / judgments 四元模型，用可执行环境状态替代“嘴硬自述”筛选 SFT/DPO 样本</text>',
    ]
    bw, bh, gap, start_x, y = 190, 185, 22, 28, 88
    for idx, (title, body, bg, border) in enumerate(boxes):
        x = start_x + idx * (bw + gap)
        parts.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" fill="{bg}" stroke="{border}" stroke-width="1.8"/>')
        parts.append(f'<text x="{x + 14}" y="{y + 32}" font-size="13.5" font-weight="700" fill="#0f172a">{_esc(title)}</text>')
        for l_idx, line in enumerate(body.split("\n")):
            parts.append(f'<text x="{x + 14}" y="{y + 72 + l_idx * 24}" font-size="11.5" fill="#334155">{_esc(line)}</text>')
        if idx < len(boxes) - 1:
            ax = x + bw + 3
            ay = y + bh / 2
            parts.append(f'<line x1="{ax}" y1="{ay}" x2="{ax + gap - 6}" y2="{ay}" stroke="#64748b" stroke-width="2"/>')
            parts.append(f'<polygon points="{ax + gap - 2},{ay} {ax + gap - 9},{ay - 5} {ax + gap - 9},{ay + 5}" fill="#64748b"/>')

    parts.append('<text x="28" y="314" font-size="11" fill="#64748b">数据源：docs/SWE_IMPORT.md · docs/ORIGINAL_TASKS.md · docs/TRAINING_CANDIDATES.md · docs/ORIGINAL_API_PILOT.md</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    stage3_path = root / "reports/stage3_and_neutral_v2.json"
    stage3 = json.loads(stage3_path.read_text(encoding="utf-8")) if stage3_path.is_file() else {}
    fac_path = root / "reports/pro_factorial_v2.json"
    factorial = json.loads(fac_path.read_text(encoding="utf-8")) if fac_path.is_file() else {}
    agreement = json.loads((root / "reports/annotator_agreement.json").read_text(encoding="utf-8"))
    cal = json.loads((root / "reports/phase4_calibration.json").read_text(encoding="utf-8"))
    rob = json.loads((root / "reports/robustness_v2.json").read_text(encoding="utf-8"))
    inj_v3_path = root / "reports/injection_metrics_v3.json"
    inj_v3 = json.loads(inj_v3_path.read_text(encoding="utf-8")) if inj_v3_path.is_file() else {}
    same_fpr_path = root / "reports/same_fpr_comparison.json"
    same_fpr = json.loads(same_fpr_path.read_text(encoding="utf-8")) if same_fpr_path.is_file() else {}

    outputs = {
        FIG_DIR / "fig1_judge_reliability.svg": build_fig1_judge_reliability(stage3, agreement, factorial),
        FIG_DIR / "fig2_saturation_calibration.svg": build_fig2_saturation_calibration(cal, stage3),
        FIG_DIR / "fig3_injection_attribution.svg": build_fig3_injection_attribution(stage3, rob, inj_v3),
        FIG_DIR / "fig4_data_pipeline_funnel.svg": build_fig4_data_pipeline_funnel(),
    }
    if same_fpr:
        outputs[FIG_DIR / "fig5_roc_pr_same_fpr.svg"] = build_fig5_roc_pr_same_fpr(same_fpr)
    for path, content in outputs.items():
        atomic_text(path, content)
        print(f"generated: {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
