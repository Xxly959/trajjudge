# TrajJudge 对外口径总表 (`CLAIMS.md`)

最后核验：2026-11-19 · 适用范围：`README.md`、`README_en.md`、`reports/FINAL_REPORT_v2.md`、`reports/showcase.html` 与简历。

**硬性口径规则（P0-1）**：
1. 所有对外引用的数字必须能在下表查到唯一出处，禁止自创或四舍五入后跨文件不一致。
2. 分母 `< 30` 的比较一律写 `x/n`（分子/分母），**禁用“翻倍 / 提升 N 倍 / 降 N 倍”**。
3. 置信区间跨 `0`、或以人工盲标（`κ = 0.250 < 0.60`）为参照的指标一律标为 **exploratory**。
4. 已撤回口径（v1 单轨迹 `75%` 与 Stage 3 泄漏 `6.25%`）单独归入「已撤回记录」表，仅作自我纠错案例，不得作为有效正面结论引用。

---

## 1. 语料、去重与人工标注一致性（Gate A）

| ID | 指标 | 数值 (`x/n`) | 场景数 | 95% 簇 CI | 检验方法 | 定性 | 来源 JSON |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- | :--- |
| `C-DATA-01` | P2 实采轨迹与去重独立场景 | `87` 条轨迹 / `51` 个 `task_id` → `36` 独立场景 | 36 | — | 静态结构指纹 | `deterministic` | `reports/scenario_map.csv` |
| `C-DATA-02` | 冻结盲标集有效标注数 | `48/50`（2 条空白按审计日志退役） | 28 | — | 冻结清单核验 | `deterministic` | `reports/annotator_agreement.json` |
| `C-ANN-01` | 双轮盲标原始一致率（全量） | `66.7%` (`32/48`) | 28 | — | 比例统计 | `exploratory` | `reports/annotator_agreement.json` |
| `C-ANN-02` | 双轮盲标 Cohen's `κ`（全量） | `0.250` (`PABAK = 0.333`) | 28 | `[-0.045, 0.505]` | 场景簇 Bootstrap (B=2000) | `exploratory` | `reports/annotator_agreement.json` |
| `C-ANN-03` | 双轮盲标 `κ`（剔除 2 处首轮笔误） | `0.309` (`n = 46`) | 28 | `[0.005, 0.559]` | 场景簇 Bootstrap (B=2000) | `exploratory` | `reports/annotator_agreement.json` |

---

## 2. RQ1 评分器可靠性、2×2 消融与同误杀率对比（探索性人工参照 `v2`）

> 注：因人工复测 `κ = 0.250 < 0.60`，本节所有以人工标签为参照的指标均定性为 **`exploratory`**。`v1`（16 失败）与 `round2`（16 失败）对照见源 JSON；所有配对默认阈值 McNemar 检验 `p ≥ 0.25`。

| ID | 评分器与模型配置 | 默认阈值失败召回 (`x/14`) | 正常样本误杀 (`x/n`) | Cohen's `κ` (95% 簇 CI) | `ROC-AUC` | `PR-AUC` (95% 簇 CI) | `Recall@FPR=10%` (step / interp) | `Recall@FPR=20%` (step / interp) | 场景数 | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :--- | :---: | :--- | :---: | :---: | ---: | :--- | :--- |
| `C-RQ1-01` | Comprehensive · Flash (`≥0.60`) | `0/14` (`0.0%`) | `0/34` (`0.0%`) | `0.000` (不可估) | `0.744` | `0.558` `[0.398, 0.687]` | `42.9%` / `42.9%` | `50.0%` / `50.0%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-02` | Accuracy · Flash (`≥2.0`) | `1/14` (`7.1%`) | `1/34` (`2.9%`) | `0.056` `[0.000, 0.187]` | `0.556` | `0.333` `[0.171, 0.483]` | `14.3%` / `20.5%` | `14.3%` / `29.4%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-03` | Accuracy · v4-Pro (`≥2.0`) | `1/14` (`7.1%`) | `2/34` (`5.9%`) | `0.016` `[-0.047, 0.113]` | `0.506` | `0.295` `[0.152, 0.426]` | `7.1%` / `11.2%` | `7.1%` / `21.1%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-04` | Evidence-Grounded · Flash (`≥0.50`, `n=47`) | `2/14` (`14.3%`) | `3/33` (`9.1%`) | `0.064` `[-0.112, 0.288]` | `0.530` | `0.363` `[0.156, 0.518]` | `14.3%` / `15.1%` | `14.3%` / `24.6%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-05` | Evidence-Grounded · v4-Pro (`≥0.50`, `n=46`) | `3/14` (`21.4%`) | `3/32` (`9.4%`) | `0.144` `[-0.085, 0.432]` | `0.557` | `0.375` `[0.189, 0.534]` | `21.4%` / `22.0%` | `21.4%` / `30.6%` | 27 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-06` | Claw-Eval 任务专属 Rubric (二值) | `5/14` (`35.7%`) | `0/34` (`0.0%`) | `0.440` `[0.101, 0.780]` | `0.679` | `0.545` `[0.286, 0.792]` | `35.7%` / `42.1%` | `35.7%` / `48.6%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |

| ID | 配对对比与校准 / 离线消融结论 | 数值 (`x/n`) | 场景数 | 95% 簇 CI / 检验 | 定性 | 来源 JSON |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- |
| `C-RQ1-07` | 通用 Accuracy 从 Flash 升至 v4-Pro 失败召回差 | `1/14 → 1/14` (`0/14` 变化) | 28 | Exact McNemar `p = 1.000` | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-08` | Pro Grounded vs Flash Comprehensive 默认阈值配对 | `3/14` vs `0/14` (`b=0, c=3`) | 27 | Exact McNemar `p = 0.250` | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-09` | 同误杀率对比一句话结论（P0-4） | **没有**：`FPR=10%` 处 `Comprehensive` 插值召回 `42.9%` 高于 `Pro Grounded` `22.0%`（`PR-AUC` `0.558` vs `0.375`） | 28 | `FPR=10%` CI `[4.8%, 66.7%]` vs `[3.6%, 42.8%]` | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-CAL-01` | 28 折 LOSO 均衡目标 · `Comprehensive` (`v1` 16 失败) | 仍漏判 `10/16` (`62.5%`)，误杀 `5/32` (`15.6%`)，`κ = 0.237` | 28 | OOF `AUC = 0.675` `[0.516, 0.791]` | `exploratory` | `reports/phase4_calibration.json` |
| `C-CAL-02` | 28 折 LOSO `miss ≤ 25%` 目标 · `Comprehensive` (`v1`) | 漏判 `1/16` (`6.25%`)，代价误杀 `23/32` (`71.9%`) | 28 | `κ = 0.163` | `exploratory` | `reports/phase4_calibration.json` |
| `C-CAL-03` | 28 折 LOSO · `Accuracy` (`v1` 16 失败) | `AUC = 0.546`（CI 覆盖 0.5）；`miss ≤ 50%/25%/10%` 全退化为 `always_fail`（误杀 `32/32`） | 28 | OOF `AUC` CI `[0.500, 0.610]` | `exploratory` | `reports/phase4_calibration.json` |
| `C-VETO-01` | 离线 P1-6 Veto 覆写比例（全部已有 Grounded 有效行） | `0/109` (`0.0%`)；`structural_veto = 0/109` | 28 | 确定性计数（Flash 原 47 + 扰 16 + Pro 原 46） | `deterministic` | `reports/veto_ablation_offline.json` |

---

## 3. RQ2 重复稳定性与上游 OpenJudge 源码贡献

| ID | 指标 / 贡献 | 数值 (`x/n`) | 场景数 / 面板数 | 95% 簇 CI / 状态 | 定性 | 来源 |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- |
| `C-RQ2-01` | OpenJudge PR #246（`TrajectoryAccuracyGrader` 保留 `raw_score`） | **已合入** `agentscope-ai/OpenJudge:main` (`c58d1d6`) | 6 项单测 | Merged | `deterministic` | `contributions/openjudge/PR_DRAFT.md` |
| `C-RQ2-02` | `VotingEvaluationStrategy` 连续分退化为 `min-of-3` 比例 | `15/22` (`68.2%`) 面板等于最小值；`9/22` (`40.9%`) 三抽样互异 | 22 面板 | 41/41 面板完全复现上游逻辑 | `deterministic` | `reports/robustness_v2.json` |
| `C-RQ2-03` | OpenJudge Issue #247 & PR #248（暴露平局元数据与文档说明） | Issue #247 **已关闭**，修复 PR #248 **已合入** (`15d22f2`) | 15 项策略单测 | Merged / Closed | `deterministic` | `contributions/openjudge/PR_DRAFT_247.md` |

---

## 4. RQ3 间接提示注入、无攻击噪声底与防御副作用（P0-3 新口径）

> 新口径要求每个注入臂并列给出：**主指标决策翻转率 (`fail→pass / base_fail`)**、**次指标归一化分差 `Δ / (max - min)`**、**传统涨分率与无攻击重复噪声底**、**有效配对数**。

| ID | 对照臂 (`Comprehensive` 量表 `[0, 1]`；`Accuracy` 量表 `[1, 3]`) | 有效配对 (`n_traj`, 场景) | 主指标决策翻转率 (`fail→pass / base_fail`) | 归一化分差 `Δ/(max-min)` (95% 簇 CI) | 涨分率 vs 无攻击噪声底 | 检验 / 状态 | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :--- | :---: | :--- | :--- | :--- |
| `C-RQ3-01` | 无攻击噪声底 · `Comprehensive` 未防御 (`r=0,1,2`) | `96` 有序对 (`16` 轨迹 / `11` 场景) | 未定义 (`0/0`，基线全过) | `mean \|Δ\| = 0.0323` | 噪声底 `43.8%` (`42/96`) | 重复测量基线 | `deterministic` | `reports/injection_metrics_v3.json` |
| `C-RQ3-02` | 无攻击噪声底 · `Comprehensive` 安全声明 (`r=0,1,2`) | `88` 有序对 (`16` 轨迹 / `11` 场景) | 未定义 (`0/0`，基线全过) | `mean \|Δ\| = 0.0299` | 噪声底 `38.6%` (`34/88`) | 重复测量基线 | `deterministic` | `reports/injection_metrics_v3.json` |
| `C-RQ3-03` | `Comprehensive` 未防御 · `L3_notice/tool_result` (全 3 轮) | `47/48` (`16` 轨迹 / `11` 场景) | 未定义 (`0/0`，基线全过) | `+0.0540` `[+0.034, +0.077]` | `89.4%` (`42/47`) vs 噪声底 `43.8%` | Holm `p_adj = 0.0078` (16 检验族) | `confirmatory` | `reports/injection_metrics_v3.json`, `reports/phase3_scenario.json` |
| `C-RQ3-04` | `Comprehensive` 安全声明 · `L3_notice/tool_result` (全 3 轮) | `44/48` (`16` 轨迹 / `11` 场景) | 未定义 (`0/0`，基线全过) | `+0.0144` `[+0.004, +0.027]` | `45.5%` (`20/44`) ≈ 噪声底 `38.6%` | 描述性对比 | `exploratory` | `reports/injection_metrics_v3.json` |
| `C-RQ3-05` | `Accuracy` 未防御 · `L3_notice/tool_result` (全 3 轮) | `48/48` (`16` 轨迹 / `11` 场景) | `2/3`（`n_scenario=1`，Case Study） | `+0.0729` | `10.4%` (`5/48`) vs 噪声底 `4.2%` | Holm `p_adj = 1.0` | `exploratory` | `reports/injection_metrics_v3.json` |
| `C-RQ3-06` | 安全声明副作用：结构化输出校验失败率（P4 1,728 行） | `864` vs `864` | — | — | `2.20%` (`19/864`) vs `0.93%` (`8/864`) | Fisher 精确检验 `p = 0.0504` | `exploratory` | `reports/robustness_v2.json` |
| `C-RQ3-07` | Phase 5 中性对照三臂差值 (`security − neutral`, `r=0`, `schema_retries=2`) | `10/16` 有效配对 (`10` 场景) | 未定义 (`0/0`) | `-0.0482` `[-0.097, -0.007]` | 中性 `9/10` (`90.0%`) vs 安全 `7/16` (`43.8%`) | 簇符号置换 `p = 0.0273`（1,024 精确置换；剩余 6/32 为 DeepSeek `json_object` 缺失 `step_evaluations`，需 `json_schema` 厂商补齐至 `≥14/16`） | `provisional` | `reports/stage3_and_neutral_v2.json`, `reports/injection_metrics_v3.json` |

---

## 5. Track B 数据工程、原创容器题与离线测试

| ID | 指标 | 数值 (`x/n`) | 定性 | 来源 |
| :--- | :--- | :--- | :--- | :--- |
| `C-TRK-01` | 跨源统一轨迹快照（Claw-Eval + SWE-bench） | `87 + 8 = 95` 条轨迹 | `deterministic` | `docs/SWE_IMPORT.md` |
| `C-TRK-02` | 原创题防刷分对照（只看末轮声明误选无产物幻觉） | `2/2` 误选无产物幻觉；可执行 Verifier `16/16` 通过并过 `TRL 0.29` | `deterministic` | `docs/TRAINING_CANDIDATES.md`, `docs/ORIGINAL_API_PILOT.md` |
| `C-ENG-01` | 离线禁网单测数量 | `534` 项（含 P0-2/P1-5 防泄漏守卫、P0-3/P0-4 统计与 P1 τ-bench/多厂商/消融单测） | `deterministic` | `tests/` |
| `C-COST-01` | 截至 v2 累计保守预算 guard 支出 | `$10.751405`（v1 `$9.180483` + v2 `$1.570922`，远低于 v2 `$5.00` 上限） | `deterministic` | `docs/BUDGET_v2.md` |

---

## 6. 已撤回口径记录（严禁作为有效结论引用）

| ID | 原表述 | 撤回原因 | 决策记录 | 替代来源 |
| :--- | :--- | :--- | :--- | :--- |
| `R-01` | v1 声称未防御 `Accuracy` 翻转率 `75% (18/24)` | 全部 24 对均来自同 1 条基线失败轨迹（`n_traj=1, n_scenario=1`），属伪重复 | `PREREG_v2.md` §6 / `V2_LOG.md` | 降级为单轨迹 Case Study；新翻转率来自 P1-1 + P1-5 |
| `R-02` | Stage 3 声称 `EvidenceGroundedGrader` 将注入膨胀率「压降 15 倍至 `6.25% (1/16)`」 | `grounded_judge.py` 中的 `_INJECTION_CUE_RE` 直接匹配 `perturb.py` 攻击模板并在扰动臂 `16/16` 触发（原始臂 `0/47`），构成测试集特征泄漏 | `docs/DECISIONS.md` **D30** | 仅允许引用 P1-5 事前冻结的 **held-out** 攻击集结果 |
| `R-03` | 旧报告声称 LOSO 均衡校准 `Comprehensive`「误杀 62.5% 正常轨迹」 | `generate_figures.py` 读取错误键名后触发硬编码回退，将均衡目标的漏判率 `62.5% (10/16)` 误作误杀率（实际均衡误杀率为 `5/32 = 15.6%`，`miss ≤ 25%` 目标误杀率为 `23/32 = 71.9%`） | 本表 `C-CAL-01` / `C-CAL-02` | 已修正 `generate_figures.py` 与全部报告 |
