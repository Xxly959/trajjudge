#!/usr/bin/env python
"""Generate offline human-review packet & templates for Module C (P1-3 & Claw-48)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from trajjudge.artifacts import atomic_text  # noqa: E402

PACKET_DIR = root / "annotation/round3_review_packet"
BLINDSPOT_CSV = root / "annotation/round3_blindspots.csv"
CLAW48_CSV = root / "annotation/round3_claw48_adjudication.csv"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _format_messages_with_indices(messages: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for idx, msg in enumerate(messages):
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role == "system":
            # Include full policy once at the top section; keep [0] compact if long
            lines.append(f"- `[{idx}]` **system**: (see Domain Policy section; length={len(content)} chars)")
            continue
        calls = msg.get("tool_calls") or []
        call_desc = ""
        if calls:
            parts = []
            for c in calls:
                fn = c.get("function") or {}
                parts.append(f"{fn.get('name')}({fn.get('arguments')})")
            call_desc = " | **tool_calls**: `" + "; ".join(parts) + "`"
        lines.append(f"- `[{idx}]` **{role}**: {content}{call_desc}")
    return lines


def prepare_review_packet() -> dict[str, Any]:
    cohort = {t["trace_id"]: t for t in json.loads((root / "outputs/p1/taubench_cohort.json").read_text(encoding="utf-8"))["traces"]}
    tau_silver = _load_jsonl(root / "outputs/p1_silver/silver_hubcore_glm_pro_taubench_passes.jsonl")
    flagged = [r for r in tau_silver if r.get("status") == "ok" and r.get("silver_label") == "fail"]

    PACKET_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Blindspot 13 review markdown
    bs_lines = [
        "# Module C1 人工复核数据包：13 条 τ-bench DB 通过轨迹疑似过程/越权盲区",
        "",
        "说明：以下 13 条轨迹均满足 τ-bench 数据库终态校验 `reward = 1.0`（`objective_pass = true`），但跨厂商特权银标（`glm-5.3`）判定存在违规或过程缺陷。请逐条阅读完整领域政策、完整对话 `[index]`、特权期望动作与银标理由，然后填写 `annotation/round3_blindspots.csv` 的 `human_verdict`（`confirmed` / `false_alarm` / `unclear`）与 `human_reason`。",
        "",
    ]
    bs_csv_rows: list[list[str]] = []
    for num, rec in enumerate(flagged, start=1):
        tid = rec["trace_id"]
        tr = cohort[tid]
        sys_policy = next((str(m.get("content") or "") for m in tr["messages"] if m.get("role") == "system"), "")
        priv = tr.get("privileged_outcome") or {}
        bs_lines.extend([
            f"---",
            f"## {num}. `{tid}` · domain=`{tr['domain']}` · scenario=`{tr['scenario_id']}` · agent=`{tr['agent_model']}`",
            "",
            f"- **AI 银标类别**: `{rec.get('primary_defect_type')}`",
            f"- **AI 引用索引**: `{rec.get('evidence_indices')}`",
            f"- **AI 银标理由**: {rec.get('rationale')}",
            f"- **Privileged `expected_actions` / `expected_outputs`**:",
            "```json",
            json.dumps(priv, ensure_ascii=False, indent=2),
            "```",
            "",
            "<details><summary>展开领域 System Policy 文本</summary>",
            "",
            "```text",
            sys_policy,
            "```",
            "</details>",
            "",
            "### 完整对话与工具轨迹（带 `[index]` 编号）",
            "",
            *_format_messages_with_indices(tr["messages"]),
            "",
        ])
        bs_csv_rows.append([
            tid,
            str(tr["domain"]),
            str(tr["scenario_id"]),
            str(rec.get("primary_defect_type") or ""),
            "",
            "",
        ])

    atomic_text(PACKET_DIR / "blindspots_13.md", "\n".join(bs_lines))
    if not BLINDSPOT_CSV.exists():
        with BLINDSPOT_CSV.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["trace_id", "domain", "scenario_id", "ai_defect_type", "human_verdict", "human_reason"])
            w.writerows(bs_csv_rows)

    # 2. Claw-48 12 disagreements review markdown
    claw_silver = _load_jsonl(root / "outputs/p1_silver/silver_hubcore_glm_pro_claw48.jsonl")
    r2_labels: dict[str, dict[str, str]] = {}
    with (root / "annotation/round2_labels.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            r2_labels[row["blind_id"]] = row

    disagreements = [
        r for r in claw_silver
        if r.get("status") == "ok" and bool(r.get("human_v2_pass")) != (r.get("silver_label") == "pass")
    ]
    claw_lines = [
        "# Module C2 人工裁定数据包：12 条 Claw-Eval 人机分歧轨迹",
        "",
        "说明：以下 12 条轨迹中，作者原 `round2_labels` (`v2`) 与跨厂商特权银标 (`glm-5.3`) 判定不一致。请对照下方原标注理由、AI 银标理由和完整脱敏轨迹，填写 `annotation/round3_claw48_adjudication.csv` 的 `final_label`（`pass` / `fail`）、`favors`（`human` / `ai` / `other`）与 `human_reason`。",
        "",
    ]
    claw_csv_rows: list[list[str]] = []
    for num, rec in enumerate(disagreements, start=1):
        bid = str(rec["blind_id"])
        r2 = r2_labels.get(bid, {})
        h_lbl = "pass" if rec.get("human_v2_pass") else "fail"
        s_lbl = str(rec.get("silver_label"))
        trace_md_path = root / "annotation/traces" / f"{bid}.md"
        trace_md = trace_md_path.read_text(encoding="utf-8") if trace_md_path.is_file() else "(trace markdown missing)"
        claw_lines.extend([
            "---",
            f"## {num}. `{bid}` · human_v2=`{h_lbl}` vs silver=`{s_lbl}` (`{rec.get('primary_defect_type')}`)",
            "",
            f"- **原 round2 人工判定**: `{r2.get('label')}` · 理由: {r2.get('reason')}",
            f"- **AI 银标引用索引**: `{rec.get('evidence_indices')}`",
            f"- **AI 银标理由**: {rec.get('rationale')}",
            "",
            "<details><summary>展开完整脱敏轨迹原文</summary>",
            "",
            trace_md,
            "</details>",
            "",
        ])
        claw_csv_rows.append([bid, h_lbl, s_lbl, "", "", ""])

    atomic_text(PACKET_DIR / "claw48_disagreements_12.md", "\n".join(claw_lines))
    if not CLAW48_CSV.exists():
        with CLAW48_CSV.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["blind_id", "human_v2_label", "silver_label", "final_label", "favors", "human_reason"])
            w.writerows(claw_csv_rows)

    return {
        "n_blindspots": len(bs_csv_rows),
        "n_claw48_disagreements": len(claw_csv_rows),
        "packet_dir": str(PACKET_DIR.relative_to(root)),
        "blindspots_csv": str(BLINDSPOT_CSV.relative_to(root)),
        "claw48_csv": str(CLAW48_CSV.relative_to(root)),
    }


def main() -> int:
    print(json.dumps(prepare_review_packet(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
