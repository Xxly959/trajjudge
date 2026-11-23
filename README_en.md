# TrajJudge

[![Offline CI](https://github.com/Xxly959/trajjudge/actions/workflows/ci.yml/badge.svg)](https://github.com/Xxly959/trajjudge/actions/workflows/ci.yml)
[![Offline Tests](https://img.shields.io/badge/Offline_Tests-547_passed-10b981)](#quick-start-offline-key-free)
[![Sockets](https://img.shields.io/badge/Network-Socket_Blocked-2563eb)](#quick-start-offline-key-free)
[![OpenJudge PR #246](https://img.shields.io/badge/OpenJudge_PR_%23246-Merged_(c58d1d6)-8957e5)](https://github.com/agentscope-ai/OpenJudge/pull/246)
[![OpenJudge PR #248](https://img.shields.io/badge/OpenJudge_PR_%23248-Merged_(15d22f2)-8957e5)](https://github.com/agentscope-ai/OpenJudge/pull/248)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **Language**: [简体中文](README.md) · English

**TrajJudge** is a trajectory-audit framework for multi-step tool-using agents, decoupling trajectory evaluation into deterministic **Evidence Ledger Extraction** (`[index]` citations + side-effect tracking), **`<untrusted_tool_data>` Quarantine Boundaries**, and **Post-Hoc Python Veto Gating**. Rather than relying on vague Likert rubrics, it transforms opaque pass/fail verdicts into auditable, tunable risk-control gates—validated against **τ-bench objective database ground truth (`n = 200`, `131` scenarios)**, a **pre-registered `n = 100` independent validation cohort** with frozen operating-point transfer, and **2 merged upstream OpenJudge PRs ([#246](https://github.com/agentscope-ai/OpenJudge/pull/246), [#248](https://github.com/agentscope-ai/OpenJudge/pull/248))**.

> **Core Architecture Takeaway**: Structured Evidence-Grounded judging does not conjure extra model discrimination out of thin air. Its engineering value lies in: (1) lifting near-broken generic rubrics (`Comprehensive`) into the usable regime with significant paired ranking gains; (2) shifting the default operating point into a high-recall region with continuous threshold tuning (`46` distinct score levels vs discrete `{1, 2, 3}`); and (3) making every verdict auditable via `[index]` evidence citations and side-effect flags.

---

## Core Empirical Findings (v3, `CLAIMS.md` & Pre-Registered Protocols)

1. **Paired `ΔAUC`, Fair D33 Control, & Two-Vendor Three-Arm Symmetry on `n = 200` Objective τ-bench Traces ([`paired_auc_v3.json`](reports/paired_auc_v3.json), [`D36`](docs/DECISIONS.md))**:
   - **vs `OpenJudge Comprehensive-D33` (Fair Reasoning-Aligned Control, `GLM-Flash`)**: Re-running `Comprehensive` on the same `200` traces under identical D33 settings (`reasoning_effort=low`, `max_tokens=4096`; `89.5%` reasoning rate, `1647` avg tokens; `147/200` valid, `53` errors, default recall `2/70 = 2.9%`) disproves the hypothesis that enabling reasoning alone rescues `Comprehensive` (`Comp-D33 vs pre-D33`: cc `+0.013, p = 0.709`; ITT `-0.006, p = 0.919`). Under fair D33 alignment, `Evidence-Grounded` remains statistically superior on both **complete-case (`n = 132`: `0.7486 vs 0.6161`, `ΔAUC = +0.1325 [+0.0058, +0.2529], p = 0.038`)** and **ITT (`n = 200`: `0.7332 vs 0.6058`, `ΔAUC = +0.1274 [+0.0210, +0.2286], p = 0.024`)** (historical pre-D33: `+0.1561 / +0.1212`), and remains significant when **pooling all `300` main+validation traces (`163` scenarios) under ITT (`+0.0921 [+0.0012, +0.1780], p = 0.049`)**.
   - **vs `OpenJudge Accuracy` (`GLM-Flash` / `GLM-Pro`)**: On complete-case (`n = 184`), `Grounded (GLM-Flash)` scores `+0.0644 (p = 0.024)`, narrowing to `+0.0446 (p = 0.184)` under ITT (`+0.0541 / +0.0307` vs `Accuracy-Pro`). Its practical advantage is operating-point placement (`63.7%` vs `27.3%`, McNemar `p = 4.66e-10`) plus continuous risk granularity instead of discrete `{1, 2, 3}` scores.
   - **Official Direct `deepseek-flash` Full 3-Arm Symmetry (`thinking=off`, `0%` reasoning, zero relay)**: Completing `DS-Comprehensive` (`198/200`, default recall `5/98 = 5.1%`, `AUC = 0.588`) shows non-significant ranking deltas without reasoning (`DS-Grounded` vs `DS-Comprehensive`: `+0.0387, p = 0.427`; vs `DS-Accuracy`: `0.0000, p = 0.973`), while still lifting default failure recall to **`48.0%`** (`+42.9 pp` over `Comprehensive`, `+31.6 pp` over `Accuracy`) with `20/27 (74.1%)` `unauthorized_side_effect` precision (`GLM-Flash`: `27/32 = 84.4%`).
2. **Pre-Registered `n = 100` Independent Validation & Operating-Point Transfer ([`PREREG_v3.md`](docs/PREREG_v3.md) Commit `54619c3`, [`p1_validation_v3.json`](reports/p1_validation_v3.json), [`operating_points_v3.json`](reports/operating_points_v3.json))**:
   - **Honest Negative Replication on `ΔAUC`**: Locked before API calls (`cohort_sha256: 6716de02...766c1`, `96% retail / 4% airline`, `80% gpt-4o`, `93` unseen), `Grounded vs Comprehensive` did not replicate ranking separation (`ΔAUC = -0.0337 [-0.273, +0.201], p = 0.840, n = 69` cc / `+0.0144, p = 0.815` ITT), though default failure recall separation persisted (`34.1%` vs `12.2%` vs `5.1%`).
   - **Verified Diagnostics (`D36`)**: Because the fair `p1d33` re-run disproved that D33 reasoning alone rescues `Comprehensive`, the validation negative replication traces to **domain shift (`airline 36.5% -> 4%`) plus small-sample `gpt-4o-retail` variance (`n = 69`, CI width `0.47`)**—not D31 prompt overfitting (`retail -> retail` `Grounded 0.6772 -> 0.6379`, `Accuracy 0.5985 -> 0.5974`), and pooling all `300` fair-D33 traces preserves significant ITT `ΔAUC (+0.092, p = 0.049)`.
   - **Operating-Point Drift**: Applying frozen main-cohort thresholds to `p1val` drops `Grounded` strict (`<0.1294`) from `37.4%/8.6%` to `9.1%/2.3%` and default (`<0.50`) from `63.7%/25.8%` to `34.1%/22.7%` (loose `<0.98125`: `87.9%/59.1% -> 77.3%/59.1%`), confirming that cross-domain deployment requires target-domain threshold recalibration—while discrete `{1, 2, 3}` `Accuracy` has no non-degenerate high-recall cutpoint (`<3.01` collapses to `100%/100%`).
3. **Component Ablation (`n = 60` Stratified Subset) & Prompt Stability**:
   - On the `60`-trace subset (an easier subset where full main `Grounded` also achieves `0.910`), point estimates decrease across `full (0.910)` -> `no_veto (0.869)` -> `no_quarantine (0.822)` -> `no_ledger (0.794)`. Common-sample paired `ΔAUC` confirms statistically significant contributions from the **Evidence Ledger** (`+0.1569, p = 0.012`) and **Tool Quarantine** (`+0.1054, p = 0.015`); **Veto** is positive but crosses zero (`+0.0413, p = 0.105`) and is retained at zero marginal API cost as a deterministic safety floor (`+7.4 pp` ablation recall, `84.4%` unauthorized-action precision). Three paraphrased prompt variants (`v0/v1/v2`) average `0.8997 ROC-AUC` (`SD = 0.0092`).
4. **Upstream OpenJudge Bugfixes & Multi-Source Engineering**:
   - Merged **[PR #246](https://github.com/agentscope-ai/OpenJudge/pull/246)** (`raw_score` observability fix) and **[PR #248](https://github.com/agentscope-ai/OpenJudge/pull/248)** (closing **[Issue #247](https://github.com/agentscope-ai/OpenJudge/issues/247)**: `15/22 = 68.2%` continuous voting panels degenerating to `min-of-3`).
   - Non-invasive HTTPX sidecar adapter + atomic checkpointing + relay model audit ([`relay_audit.json`](reports/relay_audit.json): `7,010` cache entries; `100%` GLM-family across main/`p1d33`/ablation/silver/BoN/`p1val`, with `5/675` exploratory `p15` calls routed to `nemotron`).

![Main Cohort Paired Delta-AUC & Validation Operating-Point Transfer](reports/figures/fig8_operating_points_v3.svg)

---

## Quick Start (Offline, Key-Free)

All regression tests execute with **outbound sockets blocked**, requiring no API keys or Docker to verify core logic, leakage/claims guards, and all 8 SVG deliverable figures.

```bash
# 1. Prepare pinned read-only upstream dependencies alongside this repo
git clone https://github.com/agentscope-ai/OpenJudge.git OpenJudge
git -C OpenJudge checkout 7d27246484e91c6ed4a349b6ebe7bd4629d9378f
git clone https://github.com/claw-eval/claw-eval.git claw-eval
git -C claw-eval checkout 5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7

# 2. Create virtualenv and run secret scan + socket-blocked unit tests
cd my-project
make install
make install-openjudge
make secrets
make test

# 3. Regenerate all 8 SVG figures and offline interactive dashboard
make figures
make showcase
```

For live API runs, copy `.env.example` to `.env`. Experiment drivers default to cost estimation only; live requests require explicit `--run --cap-usd`.

---

## Main Experiment Summary (τ-bench `n = 200` / `131` Scenarios)

| Grader & Model | Valid (`n/200`, Scen.) | Default Recall (`x/n`) | Default FPR (`x/n`) | Cohen's `κ` (95% CI) | `ROC-AUC` | `PR-AUC` | `R@FPR=10% / 20%` |
| :--- | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| **Evidence-Grounded · GLM-Flash** | `184/200` (`123`) | **`58/91` (`63.7%`)** | `24/93` (`25.8%`) | **`0.380`** `[0.231, 0.514]` | **`0.755`** | **`0.739`** | **`37.4%` / `60.4%`** |
| Evidence-Grounded · GLM-5.3 Pro | `198/200` (`129`) | `68/99` (`68.7%`) | `38/99` (`38.4%`) | `0.303` `[0.177, 0.436]` | `0.683` | `0.665` | `30.0%` / `51.5%` |
| **Evidence-Grounded · DeepSeek-Flash** | `197/200` (`130`) | `47/98` (`48.0%`) | `27/99` (`27.3%`) | `0.207` `[0.076, 0.341]` | `0.629` | `0.616` | `21.4%` / `39.6%` |
| OpenJudge Accuracy · GLM-5.3 Pro | `200/200` (`131`) | `21/100` (`21.0%`) | `4/100` (`4.0%`) | `0.170` `[0.086, 0.261]` | `0.703` | `0.665` | `36.4%` / `58.1%` |
| OpenJudge Accuracy · GLM-Flash | `199/200` (`131`) | `27/99` (`27.3%`) | `8/100` (`8.0%`) | `0.193` `[0.091, 0.308]` | `0.686` | `0.641` | `32.7%` / `55.7%` |
| OpenJudge Accuracy · DeepSeek-Flash | `200/200` (`131`) | `16/100` (`16.0%`) | `3/100` (`3.0%`) | `0.130` `[0.045, 0.217]` | `0.620` | `0.601` | `33.0%` / `40.4%` |
| OpenJudge Comprehensive · GLM-Flash (pre-D33 / D33) | `183` / `147` | `4/91 (4.4%)` / `2/70 (2.9%)` | `1/92` / `0/77` | `0.033` `[0.000, 0.074]` | `0.628` / `0.631` | `0.630` | `21.2%` / `31.9%` |
| OpenJudge Comprehensive · DeepSeek-Flash (Direct `0%` Thinking) | `198/200` (`131`) | `5/98` (`5.1%`) | `2/100` (`2.0%`) | `0.031` `[-0.010, 0.078]` | `0.588` | `0.607` | `21.4%` / `32.0%` |
| Rule · `observation_information_gain` | `200/200` (`131`) | `8/100` (`8.0%`) | `4/100` (`4.0%`) | `0.040` `[-0.031, 0.109]` | `0.612` | `0.600` | `14.0%` / `29.0%` |

- **Exploratory & Pending Items**: `P1-5` held-out indirect injection (`exploratory`, `10/134 = 7.5%` vs `7/55 = 12.7%`, overlapping CIs); `P2-A` Best-of-4 (`exploratory`, only `25/50` mixed-outcome tasks, `45.5%` vs random `42.0%`, null effect); `P1-3` Silver-Label blindspot screening (`13/92` DB-pass candidates + `12` Claw-48 disagreements) currently in **`pending_human_review`** (`reports/p13_human_review.json`); early Claw-Eval 48-trace manual labels (`κ = 0.250`) archived in [FINAL_REPORT_v3.md Appendix A](reports/FINAL_REPORT_v3.md).

---

## Repository Structure

```text
src/trajjudge/            Core library (taubench_adapter, grounded_judge, openjudge_bridge, llm, perturb_v3, calibration)
scripts/                  Experiment drivers, paired_auc/operating_points/relay_audit, P1-3 review kit & 8 SVG / HTML builders
tasks/original/           Original Harbor containerized coding tasks & 5 black-box verifiers
contributions/openjudge/  Merged OpenJudge PR #246 / PR #248 patches and Issue #247 archive
reports/                  FINAL_REPORT_v3.md, 8 SVG figures, showcase.html & aggregated JSON reports
docs/                     CLAIMS.md registry, RESUME_BULLETS_v3.md, PREREG_v3.md, DECISIONS.md & archive/
notes/walkthrough/        8 milestone cards & interview prep guides (including 07 blindspots & 08 paired ΔAUC)
tests/                    Offline socket-blocked unit tests (leakage, claims/wording & secret guards)
```

---

## Known Limitations & Disclosures

1. **Third-Party Relay & Vendor Scope ([`D32 / D34 / D35 / D36`](docs/DECISIONS.md))**: GLM runs executed via `api.hubcore.cn`, audited against `.cache/llm/` `raw_response.model` ([`relay_audit.json`](reports/relay_audit.json), `7,010` cache entries audited: `100%` GLM-family across main/`p1d33`/ablation/silver/BoN/`p1val`, with `5/675` exploratory `p15` routed to `nemotron`); official `deepseek-flash` (all 3 arms `thinking=off`) serves as the direct vendor baseline.
2. **Independent Validation & Offline Reranking Limits**: Pre-registered `n = 100` validation (`96% retail`) did not replicate `Grounded vs Comprehensive` `ΔAUC`, driven by `airline -> retail` domain shift and small-sample `gpt-4o-retail` variance (`p1d33` fair control disproved that D33 reasoning alone rescues `Comprehensive`, and pooled `300`-trace fair-D33 ITT remains `+0.092, p = 0.049`); cross-domain threshold calibration is required. Pure offline Best-of-4 reranking yields a null effect over random on mixed tasks.
3. **Human Review & Neutral Control Status**: Phase 5 neutral-control paired comparison (`10/16`) remains `provisional`; `P1-3` Silver-Label `13/92` blindspot candidates await blinded human adjudication (`scripts/prepare_p13_review.py` -> `scripts/summarize_p13_review.py`).
4. **Privacy**: Raw trajectories, private human labels, review packets, and API caches are gitignored and checked in CI.

> **Collaboration Note**: Implemented with AI coding assistance; experimental design, statistical calibration, and final verification were directed by the author.
