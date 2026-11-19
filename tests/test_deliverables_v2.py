"""Offline verification tests for publication figures and static HTML showcase."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def test_generate_figures_builds_valid_privacy_clean_svgs() -> None:
    res = subprocess.run([sys.executable, str(ROOT / "scripts/generate_figures.py")],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    expected = (
        "fig1_judge_reliability.svg",
        "fig2_saturation_calibration.svg",
        "fig3_injection_attribution.svg",
        "fig4_data_pipeline_funnel.svg",
        "fig5_roc_pr_same_fpr.svg",
        "fig6_p1_taubench_and_ablation.svg",
    )
    for name in expected:
        path = ROOT / "reports/figures" / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("<svg ") and text.strip().endswith("</svg>")
        assert not UUID_RE.search(text), f"UUID leaked into {name}"
        assert "sk-" not in text


def test_build_showcase_html_is_offline_self_contained_and_uuid_free() -> None:
    res = subprocess.run([sys.executable, str(ROOT / "scripts/build_showcase_html.py")],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    html_path = ROOT / "reports/showcase.html"
    assert html_path.is_file()
    content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content and "TrajJudge" in content
    # Must not load external scripts or stylesheets so offline/airgapped viewing works.
    assert not re.search(r'<(?:script|link)\b[^>]+(?:src|href)=["\']https?://', content, re.IGNORECASE)
    assert not UUID_RE.search(content), "raw trace UUID leaked into showcase.html"
    assert "sk-" not in content
