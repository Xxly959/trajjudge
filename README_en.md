# TrajJudge

[![Offline CI](https://github.com/Xxly959/trajjudge/actions/workflows/ci.yml/badge.svg)](https://github.com/Xxly959/trajjudge/actions/workflows/ci.yml)
[![Offline Tests](https://img.shields.io/badge/offline_tests-534_passed-10b981)](#quick-start-offline-no-api-key)
[![Sockets](https://img.shields.io/badge/network_in_tests-blocked-2563eb)](#quick-start-offline-no-api-key)
[![OpenJudge PR #246](https://img.shields.io/badge/OpenJudge_PR_%23246-merged_(c58d1d6)-8957e5)](https://github.com/agentscope-ai/OpenJudge/pull/246)
[![OpenJudge PR #248](https://img.shields.io/badge/OpenJudge_PR_%23248-merged_(15d22f2)-8957e5)](https://github.com/agentscope-ai/OpenJudge/pull/248)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **Language**: [简体中文主站 (README.md)](README.md) · English
>
> **Key Links**: [v3 Technical Report (Primary)](reports/FINAL_REPORT_v3.md) · [Verified Claims Registry (CLAIMS.md)](docs/CLAIMS.md) · [Interactive HTML Audit Showcase](reports/showcase.html) · [Pre-Registration v3](docs/PREREG_v3.md) · [Decisions & Retractions](docs/DECISIONS.md) · [Walkthrough Cards](notes/walkthrough/)

**One-line positioning**: **TrajJudge** is a trajectory meta-evaluation and quality-audit framework for multi-step tool-using LLM agents — diagnosing generic LLM-as-a-Judge failure modes on database-verified trajectories (τ-bench), demonstrating monotonic gains from an evidence-ledger + quarantine + veto architecture, and keeping upstream checkouts ([Claw-Eval](https://github.com/claw-eval/claw-eval), [OpenJudge](https://github.com/agentscope-ai/OpenJudge)) strictly read-only.

### Four Core Empirical Findings (all figures sourced from [docs/CLAIMS.md](docs/CLAIMS.md))

1. **Objective-label τ-bench benchmark (200 traces / 131 deduplicated scenarios): Evidence-Grounded leads on every metric while scaling a generic judge yields zero gain**: On a balanced DB-verified cohort (100 failures / 100 passes, 50/50 across DeepSeek-V3.2 and GPT-4o), `EvidenceGroundedGrader (glm-5.3-flash)` achieves **`ROC-AUC = 0.755`**, **`PR-AUC = 0.739`**, **`Recall@FPR=10% = 37.4%`**, **`Recall@FPR=20% = 60.4%`**, and **`κ = 0.380`**, significantly outperforming `OpenJudge Comprehensive` (exact McNemar fail `p = 3.55e-15`, accuracy `p = 0.00064`) and `OpenJudge Accuracy Flash/Pro` (fail `p = 4.66e-10` / `3.64e-12`, accuracy `p = 0.0328` / `0.0183`). Upgrading generic `Accuracy` from Flash to Pro gives no significant improvement (`27/99 → 21/100`, `p = 0.167`).
2. **Monotonic 4-way component ablation & cross-vendor `unauthorized_side_effect` replication**: On a stratified 60-trace τ-bench subset (`glm-5.3-flash`), removing components monotonically degrades `ROC-AUC` (**`full 0.910 > no_veto 0.869 > no_quarantine 0.822 > no_ledger 0.794`**) and `Recall@FPR=10%` (**`74.1% → 59.3% → 48.3% → 27.6%`**). Across two judge vendors, `unauthorized_side_effect` flags reach **`84.4%` (`27/32`, GLM-Flash)** and **`84.6%` (`22/26`, DeepSeek)** precision; a cross-vendor flagship silver-label audit (`glm-5.3`) also flags **`13/92 (14.1%)`** DB-pass traces as process/authorization blind spots.
3. **Indirect prompt injection requires an unperturbed noise-floor baseline and strict anti-leakage guards**: Unperturbed repeats on `Comprehensive` exhibit a `43.8% (42/96)` score-inflation noise floor; `L3_notice/tool_result` pushes inflation to `89.4% (42/47)` (normalized `+0.054`, Holm `p_adj = 0.0078`). Adding a security notice lowers inflation to `45.5%` near noise floor at the cost of higher validation errors (`2.20%` vs `0.93%`); the retried neutral control reached `10/16` valid pairs (`p = 0.0273`, `provisional`). The earlier Stage 3 Grounded figure (`6.25%`) was formally **retracted** under [D30](docs/DECISIONS.md) due to regex template leakage; the frozen 15-template held-out suite (P1-5) is checkpointed and awaits GLM credit top-up.
4. **Two upstream OpenJudge defects fixed and merged into `main`**: Preserving unclamped `raw_score` in `TrajectoryAccuracyGrader` (**[PR #246](https://github.com/agentscope-ai/OpenJudge/pull/246)** merged at `c58d1d6`) and exposing tie metadata / documenting `min-of-3` degeneration (`15/22` continuous panels) in `VotingEvaluationStrategy` (**[Issue #247](https://github.com/agentscope-ai/OpenJudge/issues/247)** closed by merged **[PR #248](https://github.com/agentscope-ai/OpenJudge/pull/248)** at `15d22f2`).

![P1 Objective-Label tau-bench Benchmark and 4-Way Component Ablation](reports/figures/fig6_p1_taubench_and_ablation.svg)

---

## Quick Start (Offline, No API Key)

All regression tests run with network sockets blocked and LLM replies mocked — no API key or Docker daemon required.

```bash
# 1. Clone pinned read-only upstream dependencies as siblings of my-project/
git clone https://github.com/agentscope-ai/OpenJudge.git OpenJudge
git -C OpenJudge checkout 7d27246484e91c6ed4a349b6ebe7bd4629d9378f
git clone https://github.com/claw-eval/claw-eval.git claw-eval
git -C claw-eval checkout 5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7

# 2. Install isolated venv and run secret scan + offline test suite
cd my-project
make install
make install-openjudge
make secrets
make test

# 3. Rebuild deterministic SVG figures (6 charts) and offline HTML showcase from tracked JSON reports
make figures
make showcase
```

For live online runs, copy `.env.example` to `.env`, configure provider keys, and pass explicit `--run --cap-usd` bounds (default invocations only print cost estimates).

---

## Primary Benchmark Summary (τ-bench, 200 Objective Traces / 131 Scenarios)

| Judge & Model | Valid / Scens | Default Recall | False Kills | Cohen's `κ` (95% CI) | `ROC-AUC` | `PR-AUC` | `R@FPR=10% / 20%` |
| :--- | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| **Evidence-Grounded · GLM-Flash** | `184/200` (`123`) | **`58/91` (`63.7%`)** | `24/93` (`25.8%`) | **`0.380`** `[0.231, 0.514]` | **`0.755`** | **`0.739`** | **`37.4%` / `60.4%`** |
| **Evidence-Grounded · DeepSeek** *(partial)* | `161/200` (`109`) | `55/79` (`69.6%`) | `31/82` (`37.8%`) | `0.318` `[0.161, 0.453]` | `0.692` | `0.673` | `33.3%` / `47.1%` |
| Evidence-Grounded · GLM-5.3 Pro | `198/200` (`129`) | `68/99` (`68.7%`) | `38/99` (`38.4%`) | `0.303` `[0.177, 0.436]` | `0.683` | `0.665` | `30.0%` / `51.5%` |
| OpenJudge Accuracy · GLM-5.3 Pro | `200/200` (`131`) | `21/100` (`21.0%`) | `4/100` (`4.0%`) | `0.170` `[0.086, 0.261]` | `0.703` | `0.665` | `36.4%` / `58.1%` |
| OpenJudge Accuracy · GLM-Flash | `199/200` (`131`) | `27/99` (`27.3%`) | `8/100` (`8.0%`) | `0.193` `[0.091, 0.308]` | `0.686` | `0.641` | `32.7%` / `55.7%` |
| OpenJudge Comprehensive · GLM-Flash | `183/200` (`125`) | `4/91` (`4.4%`) | `1/92` (`1.1%`) | `0.033` `[0.000, 0.074]` | `0.628` | `0.630` | `21.2%` / `31.9%` |
| Rule · `observation_information_gain` | `200/200` (`131`) | `8/100` (`8.0%`) | `4/100` (`4.0%`) | `0.040` `[-0.031, 0.109]` | `0.612` | `0.600` | `14.0%` / `29.0%` |

- **P1-6 Component Ablation (60 stratified τ-bench traces, `glm-5.3-flash`)**: `full` (`ROC-AUC 0.910`, `R@10% 74.1%`) > `no_veto` (`0.869`, `59.3%`) > `no_quarantine` (`0.822`, `48.3%`) > `no_ledger` (`0.794`, `27.6%`).
- **Demoted exploratory cohort**: The earlier 48-trace human-labeled Claw-Eval cohort (`κ = 0.250`) is archived in Appendix A of [FINAL_REPORT_v3.md](reports/FINAL_REPORT_v3.md).

---

## Limitations & Checkpointed Runs

- **Two-vendor scope ([D32](docs/DECISIONS.md))**: Cross-vendor evaluation covers **DeepSeek + GLM** (the partial 161/200 DeepSeek run reflects deterministic post-D31 rescoring of saved records before official DeepSeek hit HTTP 402).
- **Checkpointed pending GLM top-up**: Remaining prompt-sensitivity variants (`v1/v2`), `P2-A` Best-of-4 reranking (165 tasks / 75 mixed, `54.85%` random vs `78.18%` oracle), and `P1-5` 15-template held-out prompt injection are code-complete and checkpointed awaiting GLM balance top-up (`HTTP 403`).
- **Neutral wrapper coverage**: Retried to `10/16` valid pairs (`p = 0.0273`); remains `provisional` until rerun with strict `json_schema` support (`≥ 14/16`).

> **AI-Assisted Development Disclosure**: Implementation was assisted by an AI coding agent; experimental design, statistical verification, retractions, and result review were performed by the author.
