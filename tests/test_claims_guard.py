"""Claims & terminology guard tests enforcing Roadmap v3 Module A3 consistency."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

BANNED_PHRASES = (
    "全指标领先",
    "全指标第一",
    "全指标超越",
    "超越全部",
    "严格单调",
    "零自评",
    "因果防注入",
    "LightClaw 评测子系统",
    "LightClaw 配套",
    "配套运行时 `LightClaw`",
    "LightClaw 在线回归门禁",
    "LightClaw PR 门禁",
    "LightClaw PR gating",
    "for `LightClaw`",
    "for LightClaw",
)

GUARDED_FILES = (
    "README.md",
    "README_en.md",
    "docs/RESUME_BULLETS_v3.md",
    "reports/FINAL_REPORT_v3.md",
    "reports/showcase.html",
    "reports/figures/fig6_p1_taubench_and_ablation.svg",
    "reports/figures/fig7_p15_injection_and_p2_bon.svg",
    "reports/figures/fig8_operating_points_v3.svg",
)


def _active_claims_text() -> str:
    text = (ROOT / "docs/CLAIMS.md").read_text(encoding="utf-8")
    # Exclude §7 已撤回口径记录 where historical retracted claims are explicitly quoted.
    marker = "## 7. 已撤回口径记录"
    return text.split(marker, 1)[0] if marker in text else text


def test_no_banned_claims_or_lightclaw_subsystem_wording() -> None:
    targets: list[tuple[str, str]] = [("docs/CLAIMS.md (active)", _active_claims_text())]
    for rel in GUARDED_FILES:
        path = ROOT / rel
        assert path.is_file(), f"missing guarded deliverable: {rel}"
        targets.append((rel, path.read_text(encoding="utf-8")))

    violations: list[str] = []
    for name, content in targets:
        for phrase in BANNED_PHRASES:
            if phrase in content:
                violations.append(f"{name}: contains banned phrase {phrase!r}")
    assert not violations, "\n".join(violations)


def test_claims_registry_has_v3_ids_and_exploratory_tags() -> None:
    active = _active_claims_text()
    for cid in ("C-P1-15", "C-P1-16", "C-P1-17", "C-VAL-01", "C-VAL-02", "C-VAL-03"):
        assert cid in active, f"missing {cid} in docs/CLAIMS.md"
    for row_id in ("C-P1-14", "C-P15-01", "C-P15-02", "C-P15-03", "C-P15-04", "C-P15-05"):
        line = next((ln for ln in active.splitlines() if f"| `{row_id}`" in ln), "")
        assert line, f"missing row {row_id} in docs/CLAIMS.md"
        assert "`exploratory`" in line, f"{row_id} must be labeled exploratory: {line}"


def test_v3_json_reports_exist_and_are_privacy_clean() -> None:
    required_reports = (
        "reports/paired_auc_v3.json",
        "reports/relay_audit.json",
        "reports/p1_validation_cohort_summary.json",
        "reports/p1_validation_v3.json",
        "reports/operating_points_v3.json",
        "reports/p13_human_review.json",
    )
    for rel in required_reports:
        path = ROOT / rel
        assert path.is_file(), f"missing report JSON: {rel}"
        text = path.read_text(encoding="utf-8")
        assert not UUID_RE.search(text), f"UUID leaked into {rel}"
        assert "tau_airline_" not in text and "tau_retail_" not in text, f"raw trace_id leaked into {rel}"
        assert "sk-" not in text, f"API key fragment leaked into {rel}"
        json.loads(text)
