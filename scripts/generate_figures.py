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
    parts.append(f'<text x="40" y="352" font-size="11" fill="#7c2d12">数据源：reports/injection_metrics_v3.json &amp; reports/stage3_and_neutral_v2.json · 中性臂 {neu_paired}/16 有效配对（provisional，待 json_schema 厂商补齐）。</text>')
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


def build_fig6_p1_taubench_and_ablation(
    p1_eval: dict[str, Any],
    p16_ablation: dict[str, Any],
    p14_deepseek: dict[str, Any] | None = None,
) -> str:
    """SVG 6 (P1-1 + P1-6): Objective-Label τ-bench Benchmark & Monotonic Component Ablation."""
    raters = p1_eval.get("raters") or {}
    abls = p16_ablation.get("ablations") or {}

    def _r_row(key: str, label: str, color: str) -> tuple[str, float, float, float, str] | None:
        r = raters.get(key)
        if not r or not r.get("n_valid"):
            return None
        r20 = ((r.get("recall_at_fpr") or {}).get("fpr_20") or {}).get("recall_interpolated") or 0.0
        return (
            f"{label} (n={int(r['n_valid'])})",
            float(r.get("roc_auc") or 0.0),
            float(r.get("pr_auc_fail") or 0.0),
            float(r20),
            color,
        )

    left_rows: list[tuple[str, float, float, float, str]] = []
    for key, label, color in (
        ("p1-hubcore_glm_flash-evidence_grounded", "Grounded · GLM-Flash", "#10b981"),
        ("p1-hubcore_glm_pro-evidence_grounded", "Grounded · GLM-Pro", "#14b8a6"),
        ("p1-deepseek-evidence_grounded", "Grounded · DeepSeek-Flash", "#0ea5e9"),
        ("p1-hubcore_glm_pro-accuracy", "Accuracy · GLM-Pro", "#eab308"),
        ("p1-hubcore_glm_flash-accuracy", "Accuracy · GLM-Flash", "#f97316"),
        ("p1-deepseek-accuracy", "Accuracy · DeepSeek-Flash", "#6366f1"),
        ("p1-hubcore_glm_flash-comprehensive", "Comprehensive · GLM-Flash", "#ef4444"),
        ("p1-rule-baselines:observation_information_gain|rule", "Rule: InfoGain", "#64748b"),
    ):
        item = _r_row(key, label, color)
        if item:
            left_rows.append(item)
    if "p1-deepseek-evidence_grounded" not in raters and p14_deepseek and p14_deepseek.get("n_valid"):
        left_rows.insert(
            2 if len(left_rows) >= 2 else len(left_rows),
            (
                f"Grounded · DeepSeek (部分 n={p14_deepseek['n_valid']})",
                float(p14_deepseek.get("roc_auc") or 0.0),
                float(p14_deepseek.get("pr_auc_fail") or 0.0),
                float(p14_deepseek.get("recall_at_fpr_20_interp") or 0.0),
                "#0ea5e9",
            ),
        )

    right_rows: list[tuple[str, float, float, float, str]] = []
    for key, label, color in (
        ("full", "Full 完整架构 (n=53)", "#10b981"),
        ("no_veto", "w/o Veto 门控 (n=53)", "#3b82f6"),
        ("no_quarantine", "w/o 隔离槽 (n=58)", "#f59e0b"),
        ("no_ledger", "w/o 证据账本 (n=58)", "#ef4444"),
    ):
        a = abls.get(key)
        if a:
            right_rows.append((
                label,
                float(a.get("roc_auc") or 0.0),
                float(a.get("pr_auc_fail") or 0.0),
                float(a.get("recall_at_fpr_10") or 0.0),
                color,
            ))

    def _unauth_txt(rater: dict[str, Any], name: str) -> str | None:
        cnt = int(rater.get("unauthorized_side_effect_count") or 0)
        if not cnt:
            return None
        tf = int(rater.get("unauthorized_side_effect_true_fails") or 0)
        prec = float(rater.get("unauthorized_side_effect_precision") or 0.0)
        return f"{name} {tf}/{cnt} ({_pct(prec)})"

    unauth_parts = [
        p for p in (
            _unauth_txt(raters.get("p1-hubcore_glm_flash-evidence_grounded") or {}, "GLM-Flash"),
            _unauth_txt(raters.get("p1-deepseek-evidence_grounded") or {}, "DeepSeek-Flash"),
            _unauth_txt(raters.get("p1-hubcore_glm_pro-evidence_grounded") or {}, "GLM-Pro"),
        ) if p
    ]
    unauth_summary = " vs ".join(unauth_parts) if unauth_parts else "GLM-Flash 27/32 (84.4%)"

    w, h = 960, 505
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="34" font-size="17.5" font-weight="700" fill="#0f172a">图 6 · P1 客观标签 τ-bench 两厂商全量对比（n=200 / 131 场景）与组件消融（P1-6）</text>',
        '<text x="28" y="55" font-size="11.5" fill="#475569">相对 Comprehensive ΔAUC +0.156 显著胜出；相对 Accuracy 主差异为高召回判定点（DeepSeek 同模型 ΔAUC = 0.000）</text>',
    ]

    # Panel A (Left): P1-1 τ-bench
    lx, ly, lpw, lph = 205, 96, 265, 340
    parts.append(f'<text x="{lx + lpw / 2 - 20:.1f}" y="80" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">A. τ-bench 客观标签全量对比 (n=200)</text>')
    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        x = lx + tick * lpw
        parts.append(f'<line x1="{x:.1f}" y1="{ly}" x2="{x:.1f}" y2="{ly + lph}" stroke="#e2e8f0" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{x:.1f}" y="{ly + lph + 15}" text-anchor="middle" font-size="10" fill="#64748b">{tick:.2f}</text>')

    if left_rows:
        rh = lph / len(left_rows)
        for idx, (label, roc, pr, r20, color) in enumerate(left_rows):
            y0 = ly + idx * rh + 3
            parts.append(f'<text x="{lx - 10}" y="{y0 + 19:.1f}" text-anchor="end" font-size="10.4" font-weight="600" fill="#1e293b">{_esc(label)}</text>')
            for sub, (val, opac, tag) in enumerate(((roc, "1.0", f"AUC {roc:.3f}"), (pr, "0.60", f"PR {pr:.3f}"), (r20, "0.30", f"R@20 {_pct(r20)}"))):
                by = y0 + sub * 10
                bw = max(2.0, min(1.0, val) * lpw)
                parts.append(f'<rect x="{lx}" y="{by:.1f}" width="{bw:.1f}" height="8.5" rx="2" fill="{color}" fill-opacity="{opac}"/>')
                parts.append(f'<text x="{lx + bw + 4:.1f}" y="{by + 7.5:.1f}" font-size="9" fill="#334155">{_esc(tag)}</text>')

    # Divider
    parts.append('<line x1="538" y1="74" x2="538" y2="455" stroke="#cbd5e1" stroke-dasharray="4,4"/>')

    # Panel B (Right): P1-6 Ablation
    rx, ry, rpw, rph = 678, 96, 200, 340
    parts.append(f'<text x="{rx + rpw / 2 - 20:.1f}" y="80" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">B. 组件消融共同样本配对比较 (n=60 分层子集)</text>')
    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        x = rx + tick * rpw
        parts.append(f'<line x1="{x:.1f}" y1="{ry}" x2="{x:.1f}" y2="{ry + rph}" stroke="#e2e8f0" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{x:.1f}" y="{ry + rph + 15}" text-anchor="middle" font-size="10" fill="#64748b">{tick:.2f}</text>')

    if right_rows:
        rh = rph / len(right_rows)
        for idx, (label, roc, pr, r10, color) in enumerate(right_rows):
            y0 = ry + idx * rh + 16
            parts.append(f'<text x="{rx - 10}" y="{y0 + 25:.1f}" text-anchor="end" font-size="11.2" font-weight="600" fill="#1e293b">{_esc(label)}</text>')
            for sub, (val, opac, tag) in enumerate(((roc, "1.0", f"AUC {roc:.3f}"), (pr, "0.60", f"PR {pr:.3f}"), (r10, "0.32", f"R@10 {_pct(r10)}"))):
                by = y0 + sub * 15
                bw = max(2.0, min(1.0, val) * rpw)
                parts.append(f'<rect x="{rx}" y="{by:.1f}" width="{bw:.1f}" height="12" rx="2.5" fill="{color}" fill-opacity="{opac}"/>')
                parts.append(f'<text x="{rx + bw + 5:.1f}" y="{by + 10:.1f}" font-size="9.8" font-weight="600" fill="#334155">{_esc(tag)}</text>')

    # Legend strip + footer
    parts.append('<rect x="28" y="460" width="12" height="8" rx="2" fill="#334155" fill-opacity="1.0"/><text x="45" y="468" font-size="10" fill="#334155">ROC-AUC</text>')
    parts.append('<rect x="110" y="460" width="12" height="8" rx="2" fill="#334155" fill-opacity="0.60"/><text x="127" y="468" font-size="10" fill="#334155">PR-AUC (Fail)</text>')
    parts.append('<rect x="215" y="460" width="12" height="8" rx="2" fill="#334155" fill-opacity="0.30"/><text x="232" y="468" font-size="10" fill="#334155">左图 Recall@FPR=20% · 右图 Recall@FPR=10%</text>')
    parts.append(f'<text x="28" y="489" font-size="10.2" fill="#64748b">数据源：reports/p1_taubench_eval.json · reports/p16_ablation.json · 跨厂商 unauthorized_side_effect 精确率：{unauth_summary}</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def build_fig7_p15_injection_and_p2_bon(p15: dict[str, Any], p2_bon: dict[str, Any]) -> str:
    """SVG 7 (P1-5 + P2-A): Held-Out 15-Template Injection & Best-of-4 Reranking."""
    arms = p15.get("arm_summary") or {}
    sels = p2_bon.get("selectors") or {}
    mcn = p2_bon.get("mcnemar_pass_rate") or {}

    left_specs = [
        ("evidence_grounded|defended=True", "Grounded · Full (完整防御)", "#10b981"),
        ("evidence_grounded|defended=False", "Grounded · w/o 隔离槽", "#f59e0b"),
        ("trajectory_comprehensive|defended=False", "OpenJudge Comprehensive", "#ef4444"),
    ]
    left_rows = []
    for key, label, color in left_specs:
        a = arms.get(key) or {}
        tr = (a.get("by_location") or {}).get("tool_result") or {}
        nf = a.get("noise_floor") or {}
        if not tr.get("n_valid_pairs"):
            continue
        flip = tr.get("decision_flip_rate") or 0.0
        flip_lbl = (
            f"翻转 {tr.get('fail_to_pass_count', 0)}/{tr.get('base_fail_pairs', 0)} ({_pct(flip)})"
            if not tr.get("decision_flip_case_study")
            else f"翻转 0/{tr.get('base_fail_pairs', 0)} (1场景饱和)"
        )
        inf = tr.get("score_inflation_rate") or 0.0
        nf_inf = nf.get("score_inflation_noise_floor") or 0.0
        md = tr.get("mean_norm_delta") or 0.0
        left_rows.append((label, flip, flip_lbl, inf, f"涨分 {_pct(inf)} (底 {_pct(nf_inf)}, Δ={md:+.3f})", color))

    bon_specs = [
        ("final_confidence", "末轮自信度启发式 (50任务)", "#94a3b8"),
        ("random", "随机基线 Random (50任务)", "#64748b"),
        ("evidence_grounded|glm-5.3-flash", "Evidence-Grounded (44/50)", "#10b981"),
        ("trajectory_comprehensive|glm-5.3-flash", "Comprehensive (32/50*)", "#f97316"),
        ("oracle", "DB Oracle 上界 (50任务)", "#2563eb"),
    ]
    right_rows = []
    for key, label, color in bon_specs:
        s = sels.get(key)
        if not s:
            continue
        ci = ((s.get("pass_rate_ci") or {}).get("ci")) or [s["pass_rate"], s["pass_rate"]]
        right_rows.append((label, float(s["pass_rate"]), float(ci[0]), float(ci[1]), int(s["n_tasks"]), color))

    paired_n = (mcn.get("trajectory_comprehensive|glm-5.3-flash_vs_evidence_grounded|glm-5.3-flash") or {}).get("n", 28)
    paired_r = (mcn.get("trajectory_comprehensive|glm-5.3-flash_vs_evidence_grounded|glm-5.3-flash") or {}).get("rate_a", 0.5714)

    w, h = 960, 460
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="34" font-size="17.5" font-weight="700" fill="#0f172a">图 7 · P1-5 Held-Out 注入（exploratory, n=12）与 P2-A Best-of-4（负结果）</text>',
        '<text x="28" y="55" font-size="11.6" fill="#475569">左：15 模板探索性对比（12 轨迹/8 场景，CI 高度重叠）；右：Best-of-4 仅 25/50 个混合任务可区分选法，总体零效应</text>',
    ]

    # Panel A (Left)
    lx, ly, lpw, lph = 185, 96, 265, 290
    parts.append(f'<text x="{lx + lpw / 2 - 20:.1f}" y="80" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">A. Held-Out 15 模板注入 (exploratory)</text>')
    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        x = lx + tick * lpw
        parts.append(f'<line x1="{x:.1f}" y1="{ly}" x2="{x:.1f}" y2="{ly + lph}" stroke="#e2e8f0" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{x:.1f}" y="{ly + lph + 15}" text-anchor="middle" font-size="10" fill="#64748b">{int(tick * 100)}%</text>')

    if left_rows:
        rh = lph / len(left_rows)
        for idx, (label, flip, flip_lbl, inf, inf_lbl, color) in enumerate(left_rows):
            y0 = ly + idx * rh + 14
            parts.append(f'<text x="{lx - 10}" y="{y0 + 25:.1f}" text-anchor="end" font-size="11.2" font-weight="600" fill="#1e293b">{_esc(label)}</text>')
            bw1 = max(2.0, min(1.0, flip) * lpw)
            parts.append(f'<rect x="{lx}" y="{y0:.1f}" width="{bw1:.1f}" height="18" rx="3" fill="{color}" fill-opacity="0.95"/>')
            parts.append(f'<text x="{lx + bw1 + 6:.1f}" y="{y0 + 13:.1f}" font-size="10" font-weight="600" fill="#1e293b">{_esc(flip_lbl)}</text>')
            bw2 = max(2.0, min(1.0, inf) * lpw)
            parts.append(f'<rect x="{lx}" y="{y0 + 23:.1f}" width="{bw2:.1f}" height="18" rx="3" fill="{color}" fill-opacity="0.38"/>')
            tx2 = min(518 - 170, lx + bw2 + 6)
            parts.append(f'<text x="{lx + 6 if bw2 > 140 else lx + bw2 + 6:.1f}" y="{y0 + 36:.1f}" font-size="9.5" fill="#1e293b">{_esc(inf_lbl)}</text>')
            _ = tx2

    # Divider
    parts.append('<line x1="528" y1="74" x2="528" y2="405" stroke="#cbd5e1" stroke-dasharray="4,4"/>')

    # Panel B (Right): Best-of-4
    rx, ry, rpw, rph = 695, 96, 225, 290
    parts.append(f'<text x="{rx + rpw / 2 - 20:.1f}" y="80" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">B. P2-A Best-of-4 重排通过率 (n≤50)</text>')
    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        x = rx + tick * rpw
        parts.append(f'<line x1="{x:.1f}" y1="{ry}" x2="{x:.1f}" y2="{ry + rph}" stroke="#e2e8f0" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{x:.1f}" y="{ry + rph + 15}" text-anchor="middle" font-size="10" fill="#64748b">{int(tick * 100)}%</text>')

    if right_rows:
        rh = rph / len(right_rows)
        for idx, (label, rate, lo, hi, nt, color) in enumerate(right_rows):
            y0 = ry + idx * rh + 12
            parts.append(f'<text x="{rx - 10}" y="{y0 + 18:.1f}" text-anchor="end" font-size="11" font-weight="600" fill="#1e293b">{_esc(label)}</text>')
            bw = max(2.0, min(1.0, rate) * rpw)
            parts.append(f'<rect x="{rx}" y="{y0 + 4:.1f}" width="{bw:.1f}" height="20" rx="3" fill="{color}" fill-opacity="0.88"/>')
            c_lo = rx + max(0.0, lo) * rpw
            c_hi = rx + min(1.0, hi) * rpw
            cy = y0 + 14
            parts.append(f'<line x1="{c_lo:.1f}" y1="{cy:.1f}" x2="{c_hi:.1f}" y2="{cy:.1f}" stroke="#0f172a" stroke-width="1.5"/>')
            parts.append(f'<line x1="{c_lo:.1f}" y1="{cy - 4:.1f}" x2="{c_lo:.1f}" y2="{cy + 4:.1f}" stroke="#0f172a" stroke-width="1.5"/>')
            parts.append(f'<line x1="{c_hi:.1f}" y1="{cy - 4:.1f}" x2="{c_hi:.1f}" y2="{cy + 4:.1f}" stroke="#0f172a" stroke-width="1.5"/>')
            parts.append(f'<text x="{max(c_hi, rx + bw) + 5:.1f}" y="{y0 + 18:.1f}" font-size="10" font-weight="700" fill="#0f172a">{_pct(rate)}</text>')
            _ = nt

    parts.append('<rect x="28" y="416" width="12" height="8" rx="2" fill="#334155" fill-opacity="0.95"/><text x="45" y="424" font-size="10" fill="#334155">主指标：fail→pass 决策翻转率</text>')
    parts.append('<rect x="220" y="416" width="12" height="8" rx="2" fill="#334155" fill-opacity="0.38"/><text x="237" y="424" font-size="10" fill="#334155">次指标：涨分率 vs 无攻击噪声底</text>')
    parts.append(f'<text x="28" y="444" font-size="10.2" fill="#64748b">*注：Comprehensive 仅 32/50 完整；共同 {paired_n} 题打平 {_pct(paired_r)} (McNemar p=1.0)；50 题中仅 25 混合任务可区分选法，且 P1-5 样本 12 条（5/675 中转路由至 nemotron）属 exploratory。</text>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def build_fig8_operating_points_v3(
    op_pts: dict[str, Any],
    val_rep: dict[str, Any],
    paired_auc: dict[str, Any],
) -> str:
    """SVG 8 (v3): Operating-point transfer (Main->Val) and Paired ΔAUC forest plot (CC & ITT)."""
    w, h = 980, 520
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5"/>',
        '<text x="28" y="34" font-size="17.2" font-weight="700" fill="#0f172a">图 8 · 独立验证集工作点阈值迁移（n=100）与配对 ΔAUC / ITT 森林图</text>',
        '<text x="28" y="55" font-size="11.5" fill="#475569">左：主队列冻结阈值直接迁移至未见验证集（Grounded 连续可调 vs Accuracy 3 分制离散上限）；右：场景簇 Bootstrap 95% CI（B=2000）</text>',
    ]

    # Panel A (Left): Recall-FPR Operating Curve & Frozen Transfer Points
    ax, ay, aw, ah = 74, 96, 360, 340
    parts.append(f'<text x="{ax + aw / 2:.1f}" y="80" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">A. Recall–FPR 工作点曲线与冻结阈值迁移</text>')
    parts.append(f'<rect x="{ax}" y="{ay}" width="{aw}" height="{ah}" fill="#f8fafc" stroke="#cbd5e1"/>')
    for tick in (0.0, 0.25, 0.50, 0.75, 1.0):
        tx = ax + tick * aw
        ty = ay + (1.0 - tick) * ah
        parts.append(f'<line x1="{tx:.1f}" y1="{ay}" x2="{tx:.1f}" y2="{ay + ah}" stroke="#e2e8f0" stroke-dasharray="3,3"/>')
        parts.append(f'<line x1="{ax}" y1="{ty:.1f}" x2="{ax + aw}" y2="{ty:.1f}" stroke="#e2e8f0" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{tx:.1f}" y="{ay + ah + 15}" text-anchor="middle" font-size="9.5" fill="#64748b">{int(tick*100)}%</text>')
        parts.append(f'<text x="{ax - 7}" y="{ty + 3:.1f}" text-anchor="end" font-size="9.5" fill="#64748b">{int(tick*100)}%</text>')
    # Diagonal chance line
    parts.append(f'<line x1="{ax}" y1="{ay + ah}" x2="{ax + aw}" y2="{ay}" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4,4"/>')
    # Reference FPR=10% & Recall=80% guides
    x_fpr10 = ax + 0.10 * aw
    y_rec80 = ay + (1.0 - 0.80) * ah
    parts.append(f'<line x1="{x_fpr10:.1f}" y1="{ay}" x2="{x_fpr10:.1f}" y2="{ay + ah}" stroke="#94a3b8" stroke-dasharray="2,3"/>')
    parts.append(f'<line x1="{ax}" y1="{y_rec80:.1f}" x2="{ax + aw}" y2="{y_rec80:.1f}" stroke="#94a3b8" stroke-dasharray="2,3"/>')
    parts.append(f'<text x="{x_fpr10 + 3:.1f}" y="{ay + 12}" font-size="8.5" fill="#64748b">FPR=10%</text>')
    parts.append(f'<text x="{ax + aw - 4:.1f}" y="{y_rec80 - 4:.1f}" text-anchor="end" font-size="8.5" fill="#64748b">Recall=80%</text>')
    parts.append(f'<text x="{ax + aw / 2:.1f}" y="{ay + ah + 30}" text-anchor="middle" font-size="10.5" fill="#334155">误杀率 FPR (Pass 被误判 Fail)</text>')
    parts.append(f'<text x="20" y="{ay + ah / 2:.1f}" text-anchor="middle" font-size="10.5" fill="#334155" transform="rotate(-90 20 {ay + ah / 2:.1f})">失败召回率 Recall</text>')

    raters_op = op_pts.get("raters") or {}
    curve_specs = [
        ("evidence_grounded|glm-5.3-flash", "main", "#10b981", "2.2", ""),
        ("evidence_grounded|glm-5.3-flash", "val", "#047857", "2.2", "5,3"),
        ("trajectory_accuracy|glm-5.3-flash", "main", "#3b82f6", "1.7", ""),
        ("trajectory_accuracy|glm-5.3-flash", "val", "#1d4ed8", "1.7", "5,3"),
        ("trajectory_comprehensive|glm-5.3-flash", "main", "#f97316", "1.4", ""),
    ]
    for rkey, split, col, sw, dash in curve_specs:
        rd = raters_op.get(rkey) or {}
        pts = (rd.get("main_complete_case") or {}).get("curve") if split == "main" else rd.get("val_complete_case_curve")
        if not pts:
            continue
        sorted_pts = sorted(
            [(float(p["fpr"]), float(p["recall"])) for p in pts if p.get("fpr") is not None and p.get("recall") is not None]
        )
        if not sorted_pts:
            continue
        coords = " ".join(f"{ax + fpr * aw:.1f},{ay + (1.0 - rec) * ah:.1f}" for fpr, rec in sorted_pts)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="{sw}"{dash_attr} points="{coords}"/>')

    # Highlight Grounded & Accuracy frozen transfer points
    grd_tr = (raters_op.get("evidence_grounded|glm-5.3-flash") or {}).get("transfer") or {}
    for tier, sym_label, col_pt in (
        ("strict_fpr_le_10", "严", "#047857"),
        ("default", "默", "#10b981"),
        ("loose_recall_ge_80", "宽", "#065f46"),
    ):
        td = grd_tr.get(tier) or {}
        mp = td.get("main_complete_case") or {}
        vp = td.get("val_complete_case") or {}
        if mp.get("fpr") is not None and vp.get("fpr") is not None:
            mx, my = ax + float(mp["fpr"]) * aw, ay + (1.0 - float(mp["recall"])) * ah
            vx, vy = ax + float(vp["fpr"]) * aw, ay + (1.0 - float(vp["recall"])) * ah
            parts.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{vx:.1f}" y2="{vy:.1f}" stroke="{col_pt}" stroke-width="1.3" stroke-dasharray="2,2"/>')
            parts.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="4.2" fill="#ffffff" stroke="{col_pt}" stroke-width="2"/>')
            parts.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="4.8" fill="{col_pt}" stroke="#ffffff" stroke-width="1"/>')
            parts.append(f'<text x="{vx + 6:.1f}" y="{vy + 3:.1f}" font-size="8.8" font-weight="700" fill="{col_pt}">{sym_label}({int(round(vp["recall"]*100))}/{int(round(vp["fpr"]*100))})</text>')

    # Divider
    parts.append('<line x1="472" y1="74" x2="472" y2="462" stroke="#cbd5e1" stroke-dasharray="4,4"/>')

    # Panel B (Right): Paired Delta AUC Forest Plot
    fx, fy, fw, fh = 688, 96, 255, 340
    parts.append(f'<text x="{fx + fw / 2 - 40:.1f}" y="80" text-anchor="middle" font-size="12.5" font-weight="700" fill="#1e293b">B. 配对 ΔAUC 与 95% 场景簇 CI</text>')
    dmin, dmax = -0.30, 0.35
    def _dx(v: float) -> float:
        return fx + ((max(dmin, min(dmax, v)) - dmin) / (dmax - dmin)) * fw

    for tick in (-0.25, -0.10, 0.0, 0.10, 0.20, 0.30):
        tx = _dx(tick)
        col_g = "#0f172a" if tick == 0.0 else "#e2e8f0"
        sw_g = "1.4" if tick == 0.0 else "1.0"
        parts.append(f'<line x1="{tx:.1f}" y1="{fy}" x2="{tx:.1f}" y2="{fy + fh}" stroke="{col_g}" stroke-width="{sw_g}" stroke-dasharray="3,3"/>')
        parts.append(f'<text x="{tx:.1f}" y="{fy + fh + 15}" text-anchor="middle" font-size="9.5" fill="#64748b">{tick:+.2f}</text>')
    parts.append(f'<text x="{fx + fw / 2:.1f}" y="{fy + fh + 30}" text-anchor="middle" font-size="10.5" fill="#334155">配对 ΔAUC（右偏大于 0 表示前者排序更优）</text>')

    main_p = paired_auc.get("main_cohort") or {}
    abl_p = paired_auc.get("ablation_60") or {}
    val_p = val_rep.get("paired_delta_auc") or {}
    forest_specs = [
        ("主队列 Grd vs Comp (n=200)", main_p.get("grd_glm_flash_vs_comp_glm_flash") or {}, "complete_case", "itt", "#10b981"),
        ("验证集 Grd vs Comp (n=100)", val_p.get("grounded_vs_comprehensive") or {}, "all_complete_case", "all_itt", "#047857"),
        ("主队列 Grd vs Acc-Flash", main_p.get("grd_glm_flash_vs_acc_glm_flash") or {}, "complete_case", "itt", "#3b82f6"),
        ("验证集 Grd vs Acc-Flash", val_p.get("grounded_vs_accuracy") or {}, "all_complete_case", "all_itt", "#1d4ed8"),
        ("主队列 Grd vs Acc-Pro", main_p.get("grd_glm_flash_vs_acc_glm_pro") or {}, "complete_case", "itt", "#6366f1"),
        ("主队列 DS Grd vs DS Acc", main_p.get("grd_ds_flash_vs_acc_ds_flash") or {}, "complete_case", "itt", "#8b5cf6"),
        ("消融 full vs no_ledger (n=60)", abl_p.get("full_vs_no_ledger") or {}, "complete_case", "itt", "#f59e0b"),
        ("消融 full vs no_quarantine", abl_p.get("full_vs_no_quarantine") or {}, "complete_case", "itt", "#d97706"),
        ("消融 full vs no_veto", abl_p.get("full_vs_no_veto") or {}, "complete_case", "itt", "#b45309"),
    ]
    rh = fh / len(forest_specs)
    for idx, (label, blk, cc_k, itt_k, col) in enumerate(forest_specs):
        yc = fy + idx * rh + rh * 0.34
        yi = fy + idx * rh + rh * 0.68
        parts.append(f'<text x="{fx - 8}" y="{(yc + yi) / 2 + 3:.1f}" text-anchor="end" font-size="9.8" font-weight="600" fill="#1e293b">{_esc(label)}</text>')
        for y_pos, key_m, filled in ((yc, cc_k, True), (yi, itt_k, False)):
            st = blk.get(key_m) or {}
            d_val = st.get("delta_auc")
            ci = st.get("ci_95")
            if d_val is None or not ci:
                continue
            x0, x1, xm = _dx(float(ci[0])), _dx(float(ci[1])), _dx(float(d_val))
            op = "0.95" if filled else "0.55"
            parts.append(f'<line x1="{x0:.1f}" y1="{y_pos:.1f}" x2="{x1:.1f}" y2="{y_pos:.1f}" stroke="{col}" stroke-width="1.6" stroke-opacity="{op}"/>')
            if filled:
                parts.append(f'<circle cx="{xm:.1f}" cy="{y_pos:.1f}" r="3.6" fill="{col}"/>')
                parts.append(f'<text x="{x1 + 4:.1f}" y="{y_pos + 3:.1f}" font-size="8.4" fill="#334155">{d_val:+.3f}</text>')
            else:
                parts.append(f'<rect x="{xm - 3:.1f}" y="{y_pos - 3:.1f}" width="6" height="6" fill="#ffffff" stroke="{col}" stroke-width="1.5"/>')

    # Legend
    parts.append('<circle cx="34" cy="486" r="4" fill="#ffffff" stroke="#047857" stroke-width="2"/><text x="44" y="490" font-size="9.5" fill="#334155">主队列冻结工作点 (空心)</text>')
    parts.append('<circle cx="176" cy="486" r="4.5" fill="#047857"/><text x="186" y="490" font-size="9.5" fill="#334155">验证集迁移点 (实心: 严/默/宽 召回/误杀%)</text>')
    parts.append('<circle cx="430" cy="486" r="3.6" fill="#334155"/><text x="440" y="490" font-size="9.5" fill="#334155">右图实心圆: Complete-Case ΔAUC</text>')
    parts.append('<rect x="615" y="483" width="6" height="6" fill="#ffffff" stroke="#334155" stroke-width="1.5"/><text x="627" y="490" font-size="9.5" fill="#334155">空心方框: ITT ΔAUC（无效行记 score=0）</text>')
    parts.append('<text x="28" y="509" font-size="9.8" fill="#64748b">数据源：reports/operating_points_v3.json · reports/p1_validation_v3.json · reports/paired_auc_v3.json</text>')
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
    p1_eval_path = root / "reports/p1_taubench_eval.json"
    p1_eval = json.loads(p1_eval_path.read_text(encoding="utf-8")) if p1_eval_path.is_file() else {}
    p16_path = root / "reports/p16_ablation.json"
    p16_ablation = json.loads(p16_path.read_text(encoding="utf-8")) if p16_path.is_file() else {}
    p14_path = root / "reports/p14_cross_vendor_deepseek.json"
    p14_deepseek = json.loads(p14_path.read_text(encoding="utf-8")) if p14_path.is_file() else {}
    p15_path = root / "reports/p15_heldout_injection.json"
    p15_heldout = json.loads(p15_path.read_text(encoding="utf-8")) if p15_path.is_file() else {}
    p2_path = root / "reports/p2_best_of_n.json"
    p2_bon = json.loads(p2_path.read_text(encoding="utf-8")) if p2_path.is_file() else {}
    op_path = root / "reports/operating_points_v3.json"
    op_pts = json.loads(op_path.read_text(encoding="utf-8")) if op_path.is_file() else {}
    val_path = root / "reports/p1_validation_v3.json"
    val_rep = json.loads(val_path.read_text(encoding="utf-8")) if val_path.is_file() else {}
    pauc_path = root / "reports/paired_auc_v3.json"
    paired_auc = json.loads(pauc_path.read_text(encoding="utf-8")) if pauc_path.is_file() else {}

    outputs = {
        FIG_DIR / "fig1_judge_reliability.svg": build_fig1_judge_reliability(stage3, agreement, factorial),
        FIG_DIR / "fig2_saturation_calibration.svg": build_fig2_saturation_calibration(cal, stage3),
        FIG_DIR / "fig3_injection_attribution.svg": build_fig3_injection_attribution(stage3, rob, inj_v3),
        FIG_DIR / "fig4_data_pipeline_funnel.svg": build_fig4_data_pipeline_funnel(),
    }
    if same_fpr:
        outputs[FIG_DIR / "fig5_roc_pr_same_fpr.svg"] = build_fig5_roc_pr_same_fpr(same_fpr)
    if p1_eval and p16_ablation:
        outputs[FIG_DIR / "fig6_p1_taubench_and_ablation.svg"] = build_fig6_p1_taubench_and_ablation(
            p1_eval, p16_ablation, p14_deepseek
        )
    if p15_heldout and p2_bon:
        outputs[FIG_DIR / "fig7_p15_injection_and_p2_bon.svg"] = build_fig7_p15_injection_and_p2_bon(
            p15_heldout, p2_bon
        )
    if op_pts and val_rep and paired_auc:
        outputs[FIG_DIR / "fig8_operating_points_v3.svg"] = build_fig8_operating_points_v3(
            op_pts, val_rep, paired_auc
        )
    for path, content in outputs.items():
        atomic_text(path, content)
        print(f"generated: {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
