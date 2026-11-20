# TrajJudge 对外口径总表 (`CLAIMS.md`)

最后核验：2026-11-20 · 适用范围：`README.md`、`README_en.md`、`reports/FINAL_REPORT_v3.md`、`reports/FINAL_REPORT_v2.md`、`reports/showcase.html` 与简历。

**硬性口径规则（P0-1）**：
1. 所有对外引用的数字必须能在下表查到唯一出处，禁止自创或四舍五入后跨文件不一致。
2. 分母 `< 30` 的比较一律写 `x/n`（分子/分母），**禁用「翻倍 / 提升 N 倍 / 降 N 倍」**。
3. 置信区间跨 `0`、或以人工盲标（`κ = 0.250 < 0.60`）为参照的指标一律标为 **`exploratory`**；基于数据库可执行验证的 τ-bench 客观标签大样本指标标为 **`confirmatory`**（部分样本或单次消融如实标明样本量与范围）。
4. 已撤回口径（v1 单轨迹 `75%`、Stage 3 泄漏 `6.25%`、LOSO 误杀误报 `62.5%`）单独归入「已撤回记录」表，仅作自我纠错案例，不得作为有效正面结论引用。

---

## 1. 主实验：P1 客观标签 τ-bench 大样本验证（`n = 200` / `131` 独立场景，P1-1 & P1-4）

> **真值来源**：τ-bench 数据库可执行状态校验（`reward == 1.0` 为客观通过，零人工主观噪声），严格隔离 `reward` 与 `expected_actions` 防止泄漏（`PREREG_v3.md`）。跨 `DeepSeek-V3.2`（100 条：50 失败 / 50 通过）与 `gpt-4o`（100 条：50 失败 / 50 通过）精确 50/50 平衡，覆盖 `airline`（73 条）与 `retail`（127 条）。

### 1.1 语料与池规模

| ID | 指标 | 数值 (`x/n`) | 场景数 | 校验哈希 / 状态 | 定性 | 来源 JSON |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- |
| `C-P1-DATA-01` | 冻结 τ-bench 客观标签队列 | `200` 条（`100` 失败 + `100` 通过；DeepSeek-V3.2 `100` + GPT-4o `100`；airline `73` + retail `127`） | 131 | `SHA-256 = e460dbef...1bed73a`（源池 `825` 条零未映射角色） | `deterministic` | `reports/p1_cohort_summary.json` |
| `C-P1-DATA-02` | Best-of-4 重排候选池（P2-A） | `165` 个任务（每任务 4 次采样，其中 `75` 个混合成败任务）；随机期望通过率 `54.85%` vs 数据库 Oracle 上界 `78.18%` | 165 | 池已冻结；已抽取 50 任务完成在线裁判重排，见 `C-P2A-01..05` | `deterministic` | `reports/p1_cohort_summary.json` |

### 1.2 评分器客观标签全量对比（同误杀率与阈值无关指标）

| ID | 评分器与模型配置 | 有效数 (`n/200`, 场景) | 默认阈值召回 (`x/n`) | 默认误杀 (`x/n`) | Cohen's `κ` (95% 簇 CI) | `ROC-AUC` (95% 簇 CI) | `PR-AUC` (95% 簇 CI) | `R@FPR=10%` (step / interp) | `R@FPR=20%` (step / interp) | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| `C-P1-01` | **Evidence-Grounded · GLM-Flash** (`≥0.50`) | `184/200` (`123`) | **`58/91` (`63.7%`)** | `24/93` (`25.8%`) | **`0.380`** `[0.231, 0.514]` | **`0.755`** `[0.673, 0.825]` | **`0.739`** `[0.637, 0.830]` | **`37.4%` / `37.4%`** | **`60.4%` / `60.4%`** | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-02` | Evidence-Grounded · GLM-5.3 Pro (`≥0.50`) | `198/200` (`129`) | `68/99` (`68.7%`) | `38/99` (`38.4%`) | `0.303` `[0.177, 0.436]` | `0.683` `[0.616, 0.753]` | `0.665` `[0.573, 0.757]` | `0.0%` / `30.0%` | `51.5%` / `51.5%` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-08` | **Evidence-Grounded · DeepSeek-Flash**（官方完整 post-D31） | `197/200` (`130`) | `47/98` (`48.0%`) | `27/99` (`27.3%`) | `0.207` `[0.076, 0.341]` | `0.629` `[0.553, 0.707]` | `0.616` `[0.514, 0.717]` | `21.4%` / `21.4%` | `38.8%` / `39.6%` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-03` | OpenJudge Accuracy · GLM-5.3 Pro (`≥2.0`) | `200/200` (`131`) | `21/100` (`21.0%`) | `4/100` (`4.0%`) | `0.170` `[0.086, 0.261]` | `0.703` `[0.641, 0.764]` | `0.665` `[0.580, 0.745]` | `21.0%` / `36.4%` | `57.0%` / `58.1%` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-04` | OpenJudge Accuracy · GLM-Flash (`≥2.0`) | `199/200` (`131`) | `27/99` (`27.3%`) | `8/100` (`8.0%`) | `0.193` `[0.091, 0.308]` | `0.686` `[0.623, 0.753]` | `0.641` `[0.550, 0.728]` | `27.3%` / `32.7%` | `54.6%` / `55.7%` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-08b` | OpenJudge Accuracy · DeepSeek-Flash (`≥2.0`, 官方完整) | `200/200` (`131`) | `16/100` (`16.0%`) | `3/100` (`3.0%`) | `0.130` `[0.045, 0.217]` | `0.620` `[0.566, 0.672]` | `0.601` `[0.516, 0.681]` | `30.0%` / `33.0%` | `30.0%` / `40.4%` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-05` | OpenJudge Comprehensive · GLM-Flash (`≥0.60`) | `183/200` (`125`) | `4/91` (`4.4%`) | `1/92` (`1.1%`) | `0.033` `[0.000, 0.074]` | `0.628` `[0.538, 0.710]` | `0.630` `[0.527, 0.733]` | `20.9%` / `21.2%` | `31.9%` / `31.9%` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-06` | Rule · `observation_information_gain` | `200/200` (`131`) | `8/100` (`8.0%`) | `4/100` (`4.0%`) | `0.040` `[-0.031, 0.109]` | `0.612` `[0.533, 0.693]` | `0.600` `[0.493, 0.715]` | `14.0%` / `14.0%` | `29.0%` / `29.0%` | `deterministic` | `reports/p1_taubench_eval.json` |
| `C-P1-07` | Rule · `action_loop_detection` | `200/200` (`131`) | `0/100` (`0.0%`) | `0/100` (`0.0%`) | `0.000` (不可估) | `0.583` `[0.527, 0.639]` | `0.554` `[0.465, 0.649]` | `22.0%` / `20.0%` | `30.0%` / `35.6%` | `deterministic` | `reports/p1_taubench_eval.json` |

### 1.3 配对显著性检验、越权副作用精度与跨厂商自评偏好审计（P1-1 & P1-4，两厂商范围）

| ID | 检验 / 审计结论 | 数值 (`x/n`) | 共同样本 / 场景 | 统计检验 / 证据 | 定性 | 来源 JSON |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `C-P1-09` | Grounded (GLM-Flash) vs Comprehensive (GLM-Flash) | 失败召回 `63.9%` vs `4.8%`；总体准确率 `69.6%` vs `52.4%` | `n=168` (`49` vs `0` 仅前者抓出) | Exact McNemar 失败 `p = 3.55e-15`（21 检验族 Holm `p_adj = 7.11e-14`）；总准确率 `p = 0.00064` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-10` | Grounded (GLM-Flash) vs Accuracy (GLM-Flash) | 失败召回 `63.7%` vs `28.6%`；总体准确率 `69.0%` vs `60.3%` | `n=184` (`32` vs `0` 仅前者抓出) | Exact McNemar 失败 `p = 4.66e-10`（Holm `p_adj = 6.05e-09`）；总准确率 `p = 0.0328` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-11` | Grounded (GLM-Flash) vs Accuracy (GLM-5.3 Pro) | 失败召回 `63.7%` vs `20.9%`；总体准确率 `69.0%` vs `58.7%` | `n=184` (`39` vs `0` 仅前者抓出) | Exact McNemar 失败 `p = 3.64e-12`（Holm `p_adj = 6.18e-11`）；总准确率 `p = 0.0183` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-12` | 单纯升级通用模型无增益：Accuracy Pro vs Accuracy Flash | 失败召回 `20.2%` vs `27.3%`；总体准确率 `58.3%` vs `59.8%` | `n=199` (`13` vs `6`) | Exact McNemar 失败 `p = 0.167`（Holm `p_adj = 0.501`）；总准确率 `p = 0.690` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-12b` | DeepSeek-Flash 同底座配对与跨厂商差异 | Grounded vs Accuracy：`48.0%` vs `16.3%` 召回（`n=197`, `32` vs `1`）；总准确率 `60.4%` vs `57.4%` | `n=197` / 跨厂商 `n=181` | 同底座 Exact McNemar 失败 `p = 7.92e-09`（Holm `p_adj = 9.50e-08`），总准确率 `p = 0.512`；跨厂商 GLM-Flash vs DeepSeek-Flash Grounded 失败 `p = 0.0106`（Holm `p_adj = 0.0531`）、总准确率 `69.1%` vs `60.8%` (`p = 0.0275`) | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-13` | 跨厂商 `unauthorized_side_effect` 越权副作用精确率 | **GLM-Flash `27/32` (`84.4%`)** · **GLM-Pro `30/40` (`75.0%`)** · **DeepSeek-Flash `20/27` (`74.1%`)** | 2 厂商 (`184` / `198` / `197`) | 三次全量 Grounded 均维持 `74%–84%` 精确率；代码 Veto 覆写模型 `GLM-Flash 6/184 (3.3%)`、`GLM-Pro 0/198`、`DeepSeek-Flash 2/197 (1.0%)` | `confirmatory` | `reports/p1_taubench_eval.json` |
| `C-P1-14` | 两厂商自评偏好（Self-Preference）检查 | **GLM-Flash Grounded**：DeepSeek-V3.2 `AUC 0.781` (召回 `62.2%`, FK `20.0%`) vs GPT-4o `AUC 0.726` (召回 `65.2%`, FK `31.3%`)；**DeepSeek-Flash Grounded**：DeepSeek-V3.2 `AUC 0.659` (召回 `48.0%`, FK `26.5%`) vs GPT-4o `AUC 0.599` (召回 `47.9%`, FK `28.0%`) | 2 裁判厂商 × 2 被测 Agent | 未出现 DeepSeek 裁判放水自家 DeepSeek 轨迹的自评偏倚（`DeepSeek-Flash Accuracy` 亦为 DeepSeek 召回 `20.0%` 高于 GPT-4o `12.0%`；注：按 D32 明确为两厂商范围） | `confirmatory` | `reports/p1_taubench_eval.json` |

---

## 2. P1-6 组件消融与 P1-3 跨厂商特权银标审计

### 2.1 四路组件消融单调阶梯（60 条分层 τ-bench / `36–40` 独立场景，`glm-5.3-flash`）

| ID | 消融配置 | 有效数 / 场景 | 默认召回 / 误杀 | Cohen's `κ` | `ROC-AUC` | `PR-AUC` | `Recall@FPR=10%` | `Recall@FPR=20%` | Veto 覆写 (`x/n`) | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| `C-P16-01` | **`full`（完整架构：账本 + 隔离槽 + Veto）** | `53/60` (`36`) | `24/27` (`88.9%`) / `9/26` (`34.6%`) | **`0.545`** | **`0.910`** | **`0.898`** | **`74.1%`** | **`85.2%`** | `3/53` (`5.7%`) | `confirmatory` | `reports/p16_ablation.json` |
| `C-P16-02` | `no_veto`（关闭 Python 强制否决门控） | `53/60` (`36`) | `22/27` (`81.5%`) / `8/26` (`30.8%`) | `0.508` | `0.869` | `0.871` | `59.3%` (`-14.8 pp`) | `74.1%` | `0/53` (`0.0%`) | `confirmatory` | `reports/p16_ablation.json` |
| `C-P16-03` | `no_quarantine`（关闭工具输出隔离槽） | `58/60` (`40`) | `27/29` (`93.1%`) / `13/29` (`44.8%`) | `0.483` | `0.822` | `0.795` | `48.3%` (`-25.8 pp`) | `65.5%` | `10/58` (`17.2%`) | `confirmatory` | `reports/p16_ablation.json` |
| `C-P16-04` | `no_ledger`（移除证据账本，直审原始对话） | `58/60` (`40`) | `20/29` (`69.0%`) / `7/29` (`24.1%`) | `0.448` | `0.794` | `0.738` | `27.6%` (`-46.5 pp`) | `55.2%` | `1/58` (`1.7%`) | `confirmatory` | `reports/p16_ablation.json` |
| `C-P16-05` | 提示词敏感性（`v0 / v1 / v2` 3 套等价模板） | `v0: 53/60` (`0.910`), `v1: 58/60` (`0.895`), `v2: 56/60` (`0.894`) | `36–40` | `ROC-AUC` 均值 `0.900` (SD `0.0092`)；`PR-AUC` `0.885` (SD `0.0148`)；`R@10%` `74.1%` (SD `2.75%`)；失败召回 `92.6%` (SD `3.64%`) | — | — | — | `confirmatory` | `reports/p16_ablation.json` |

### 2.3 P2-A Best-of-4 重排闭环（`50` 个 τ-bench 任务 × 4 候选，`glm-5.3-flash`）

| ID | 选择策略 | 完整任务数 | 客观通过率 (`x/n`) | 95% 场景簇 CI | 配对比较 / 偏差审计 | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- | :--- |
| `C-P2A-01` | `random`（随机单样本期望） | `50/50` | `42.0%` | `[32.0%, 52.0%]` | 每任务 4 次采样期望通过率均值（`25` 个混合成败任务） | `deterministic` | `reports/p2_best_of_n.json` |
| `C-P2A-02` | `final_confidence`（末轮语气启发式） | `50/50` | `40.0%` (`20/50`) | `[26.0%, 54.0%]` | 略低于随机基线；在 `44` 完整任务子集上为 `43.2%` | `deterministic` | `reports/p2_best_of_n.json` |
| `C-P2A-03` | **`Evidence-Grounded` (`glm-5.3-flash`)** | `44/50` | `45.5%` (`20/44`) | `[31.8%, 59.1%]` | vs `final_confidence` (`n=44`): `45.5%` vs `43.2%` (McNemar `p = 1.0`)；混合任务子集 `44.0%` vs `43.0%` | `confirmatory` | `reports/p2_best_of_n.json` |
| `C-P2A-04` | `Comprehensive` (`32/50`) 与共同对齐对比 (`n=28`) | `32/50` / **`28`** | 表观 `53.1%` (`17/32`)；共同对齐 **`57.1%` (`16/28`) vs `57.1%` (`16/28`)** | `[34.4%, 71.9%]` | 表观高出系 `18` 个难题 `504`/Schema 缺失造成幸存者偏差；对齐 `n=28` 两裁判完全打平（McNemar `p = 1.0`） | `confirmatory` | `reports/p2_best_of_n.json` |
| `C-P2A-05` | `oracle`（数据库可执行校验上界） | `50/50` | **`72.0%`** (`36/50`) | `[58.0%, 84.0%]` | 暴露单靠无执行验证的离线轨迹排序仍存在 `26.5 pp` 差距 | `deterministic` | `reports/p2_best_of_n.json` |

### 2.4 P1-5 Held-Out 15 模板间接提示注入（`SHA-256 = 08a07040...bab30081`，`12` 失败轨迹 / `8` 场景，`glm-5.3-flash`）

| ID | 实验臂与位置（仅开发期未见过 Held-Out 攻击） | 有效配对 (场景 / 失败场景) | 主指标决策翻转率 (`fail→pass / base_fail`) | 归一化分差 `Δ/(max-min)` (95% 簇 CI) | 涨分率 vs 无攻击噪声底 | 结论与因果对照 | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :--- | :---: | :--- | :--- | :--- |
| `C-P15-01` | **`Evidence-Grounded full` · 全部 3 位置合计** | `237` (`8` / `7`) | **`8.4%` (`18/214`)** `[1.6%, 20.0%]` | `+0.0257` `[-0.117, +0.150]` | `21.1%` (`50/237`) **< 噪声底 `26.4%`** (`19/72`) | 重复翻转噪声底 `3.2%` (`2/62`)；分位置：`tool_result 7.5%`、`assistant_final 7.7%` (`3/39`)、`assistant_mid 12.2%` (`5/41`) | `confirmatory` | `reports/p15_heldout_injection.json` |
| `C-P15-02` | **`Evidence-Grounded full` · `tool_result` (全部 15 模板)** | `149` (`7` / `6`) | **`7.5%` (`10/134`)** `[0.6%, 18.5%]` | `+0.0286` `[-0.088, +0.139]` | `20.1%` (`30/149`) **< 噪声底 `26.4%`** | 含 `json_disguise` 仅 `3.5%` (`2/57`) 翻转、`zh_paraphrase 8.5%` (`5/59`)、`en_directive 10.9%` (`6/55`)、`policy_spoof 11.6%` (`5/43`) | `confirmatory` | `reports/p15_heldout_injection.json` |
| `C-P15-03` | **`Grounded no_quarantine`（关闭隔离槽）· `tool_result`** | `63` (`6` / `5`) | **`12.7%` (`7/55`)** `[0.0%, 30.4%]` | `+0.0688` `[-0.105, +0.258]` | `33.3%` (`21/63`) **> 噪声底 `18.2%`** | 移除 `<untrusted_tool_data>` 后，全部 7 次决策翻转均出自 `tool_result`；JSON 伪装翻转升至 `15.8%` (`3/19` vs `3.5%`) | `confirmatory` | `reports/p15_heldout_injection.json` |
| `C-P15-04` | `Grounded no_quarantine` · 全部位置合计与噪声底 | `91` (`7` / `5`) | `9.3%` (`7/75`) `[0.0%, 21.3%]` | `+0.0184` `[-0.155, +0.155]` | `27.5%` (`25/91`) vs 噪声底 `18.2%` (`8/44`) | 无攻击重复决策翻转噪声底由 `full` 的 **`3.2%` (`2/62`) 升至 `12.5%` (`4/32`)**，证明隔离槽亦降低基准抖动 | `confirmatory` | `reports/p15_heldout_injection.json` |
| `C-P15-05` | `OpenJudge Comprehensive` · 全部位置与 `tool_result` | `195` (`7` / **`1`**) | `0/21` (`case_study`：11/12 轨迹基线饱和 `≥0.60`) | `+0.0092` `[-0.002, +0.022]`；`zh_paraphrase` **`+0.0175` `[+0.004, +0.039]`** | `tool_result` 涨分 **`55.7%` (`68/122`)**（全部 `49.7%` vs 噪声底 `47.6%`） | 中文改写注入在统计上显著推高 `Comprehensive` 分数（CI 全正） | `exploratory` | `reports/p15_heldout_injection.json` |

### 2.2 P1-3 跨厂商特权 AI 标注者（`glm-5.3`，仅作 Silver Label）

| ID | 审计任务 | 数值 (`x/n`) | 结论与定位 | 定性 | 来源 JSON |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `C-P13-01` | 旗舰 `glm-5.3` vs 人工盲标 `v2`（Claw-Eval 48 条） | 有效 `45/48`，原始一致率 `73.3%`，`PABAK = 0.467`，`κ = 0.206` | 高于双轮人工原始一致率 `66.7%`，`12` 条分歧已导出人工裁决清单（`silver_label_only`） | `exploratory` | `reports/p13_claw48_silver_agreement.json` |
| `C-P13-02` | τ-bench 客观通过轨迹（`reward=1.0`）数据库校验盲区审计 | 有效审计 `92/100` 条，标出 **`13/92` (`14.1%`)** 疑似过程/越权盲区 | 证明单纯终态 DB 校验存在过程合规盲区，13 条案例已导出人工抽检清单（`silver_label_only`） | `exploratory` | `reports/p13_blindspot_summary.json` |

---

## 3. 附录探索性队列：早期 Claw-Eval 48 条人工盲标与校准（Gate A & RQ1 探索性）

> 注：因人工复测 `κ = 0.250 < 0.60`，本节所有以人工标签为参照的指标均定性为 **`exploratory`**，在 `FINAL_REPORT_v3.md` 中正式降级至附录 A。`v1`（16 失败）与 `round2`（16 失败）对照见源 JSON；所有配对默认阈值 McNemar 检验 `p ≥ 0.25`。

| ID | 指标 | 数值 (`x/n`) | 场景数 | 95% 簇 CI | 检验方法 | 定性 | 来源 JSON |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- | :--- |
| `C-DATA-01` | P2 实采轨迹与去重独立场景 | `87` 条轨迹 / `51` 个 `task_id` → `36` 独立场景 | 36 | — | 静态结构指纹 | `deterministic` | `reports/scenario_map.csv` |
| `C-DATA-02` | 冻结盲标集有效标注数 | `48/50`（2 条空白按审计日志退役） | 28 | — | 冻结清单核验 | `deterministic` | `reports/annotator_agreement.json` |
| `C-ANN-01` | 双轮盲标原始一致率（全量） | `66.7%` (`32/48`) | 28 | — | 比例统计 | `exploratory` | `reports/annotator_agreement.json` |
| `C-ANN-02` | 双轮盲标 Cohen's `κ`（全量） | `0.250` (`PABAK = 0.333`) | 28 | `[-0.045, 0.505]` | 场景簇 Bootstrap (B=2000) | `exploratory` | `reports/annotator_agreement.json` |
| `C-ANN-03` | 双轮盲标 `κ`（剔除 2 处首轮笔误） | `0.309` (`n = 46`) | 28 | `[0.005, 0.559]` | 场景簇 Bootstrap (B=2000) | `exploratory` | `reports/annotator_agreement.json` |

| ID | 评分器与模型配置（Claw-Eval 48 条探索性 `v2` 标签） | 默认阈值失败召回 (`x/14`) | 正常样本误杀 (`x/n`) | Cohen's `κ` (95% 簇 CI) | `ROC-AUC` | `PR-AUC` (95% 簇 CI) | `Recall@FPR=10%` (step / interp) | `Recall@FPR=20%` (step / interp) | 场景数 | 定性 | 来源 JSON |
| :--- | :--- | :---: | :---: | :--- | :---: | :--- | :---: | :---: | ---: | :--- | :--- |
| `C-RQ1-01` | Comprehensive · Flash (`≥0.60`) | `0/14` (`0.0%`) | `0/34` (`0.0%`) | `0.000` (不可估) | `0.744` | `0.558` `[0.398, 0.687]` | `42.9%` / `42.9%` | `50.0%` / `50.0%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-02` | Accuracy · Flash (`≥2.0`) | `1/14` (`7.1%`) | `1/34` (`2.9%`) | `0.056` `[0.000, 0.187]` | `0.556` | `0.333` `[0.171, 0.483]` | `14.3%` / `20.5%` | `14.3%` / `29.4%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-03` | Accuracy · v4-Pro (`≥2.0`) | `1/14` (`7.1%`) | `2/34` (`5.9%`) | `0.016` `[-0.047, 0.113]` | `0.506` | `0.295` `[0.152, 0.426]` | `7.1%` / `11.2%` | `7.1%` / `21.1%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-04` | Evidence-Grounded · Flash (`≥0.50`, `n=47`) | `2/14` (`14.3%`) | `3/33` (`9.1%`) | `0.064` `[-0.112, 0.288]` | `0.530` | `0.363` `[0.156, 0.518]` | `14.3%` / `15.1%` | `14.3%` / `24.6%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-05` | Evidence-Grounded · v4-Pro (`≥0.50`, `n=46`) | `3/14` (`21.4%`) | `3/32` (`9.4%`) | `0.144` `[-0.085, 0.432]` | `0.557` | `0.375` `[0.189, 0.534]` | `21.4%` / `22.0%` | `21.4%` / `30.6%` | 27 | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-06` | Claw-Eval 任务专属 Rubric (二值) | `5/14` (`35.7%`) | `0/34` (`0.0%`) | `0.440` `[0.101, 0.780]` | `0.679` | `0.545` `[0.286, 0.792]` | `35.7%` / `42.1%` | `35.7%` / `48.6%` | 28 | `exploratory` | `reports/same_fpr_comparison.json` |

| ID | 配对对比与校准 / 离线消融结论（Claw-Eval 48 条探索性） | 数值 (`x/n`) | 场景数 | 95% 簇 CI / 检验 | 定性 | 来源 JSON |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- |
| `C-RQ1-07` | 通用 Accuracy 从 Flash 升至 v4-Pro 失败召回差 | `1/14 → 1/14` (`0/14` 变化) | 28 | Exact McNemar `p = 1.000` | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-08` | Pro Grounded vs Flash Comprehensive 默认阈值配对 | `3/14` vs `0/14` (`b=0, c=3`) | 27 | Exact McNemar `p = 0.250` | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-RQ1-09` | 同误杀率对比一句话结论（P0-4，仅限 Claw-Eval 48 条） | **小样本探索集尚未反超**：`FPR=10%` 处 `Comprehensive` 插值召回 `42.9%` 高于 `Pro Grounded` `22.0%`（`PR-AUC` `0.558` vs `0.375`）；而在 200 条客观 τ-bench 上反转为 Grounded 全指标领先（见 `C-P1-01`） | 28 | `FPR=10%` CI `[4.8%, 66.7%]` vs `[3.6%, 42.8%]` | `exploratory` | `reports/same_fpr_comparison.json` |
| `C-CAL-01` | 28 折 LOSO 均衡目标 · `Comprehensive` (`v1` 16 失败) | 仍漏判 `10/16` (`62.5%`)，误杀 `5/32` (`15.6%`)，`κ = 0.237` | 28 | OOF `AUC = 0.675` `[0.516, 0.791]` | `exploratory` | `reports/phase4_calibration.json` |
| `C-CAL-02` | 28 折 LOSO `miss ≤ 25%` 目标 · `Comprehensive` (`v1`) | 漏判 `1/16` (`6.25%`)，代价误杀 `23/32` (`71.9%`) | 28 | `κ = 0.163` | `exploratory` | `reports/phase4_calibration.json` |
| `C-CAL-03` | 28 折 LOSO · `Accuracy` (`v1` 16 失败) | `AUC = 0.546`（CI 覆盖 0.5）；`miss ≤ 50%/25%/10%` 全退化为 `always_fail`（误杀 `32/32`） | 28 | OOF `AUC` CI `[0.500, 0.610]` | `exploratory` | `reports/phase4_calibration.json` |
| `C-VETO-01` | 离线 Veto 覆写比例（旧 Claw-Eval 全部有效 Grounded 行） | `0/109` (`0.0%`)；`structural_veto = 0/109`（而在 τ-bench 上 Veto 实际覆写 `6/184` 与 `3/53`，见 `C-P1-13` / `C-P16-01`） | 28 | 确定性计数（Flash 原 47 + 扰 16 + Pro 原 46） | `deterministic` | `reports/veto_ablation_offline.json` |

---

## 4. RQ2 重复稳定性与上游 OpenJudge 源码贡献

| ID | 指标 / 贡献 | 数值 (`x/n`) | 场景数 / 面板数 | 95% 簇 CI / 状态 | 定性 | 来源 |
| :--- | :--- | :--- | ---: | :--- | :--- | :--- |
| `C-RQ2-01` | OpenJudge PR #246（`TrajectoryAccuracyGrader` 保留 `raw_score`） | **已合入** `agentscope-ai/OpenJudge:main` (`c58d1d6`) | 6 项单测 | Merged | `deterministic` | `contributions/openjudge/PR_DRAFT.md` |
| `C-RQ2-02` | `VotingEvaluationStrategy` 连续分退化为 `min-of-3` 比例 | `15/22` (`68.2%`) 面板等于最小值；`9/22` (`40.9%`) 三抽样互异 | 22 面板 | 41/41 面板完全复现上游逻辑 | `deterministic` | `reports/robustness_v2.json` |
| `C-RQ2-03` | OpenJudge Issue #247 & PR #248（暴露平局元数据与文档说明） | Issue #247 **已关闭**，修复 PR #248 **已合入** (`15d22f2`) | 15 项策略单测 | Merged / Closed | `deterministic` | `contributions/openjudge/PR_DRAFT_247.md` |

---

## 5. RQ3 间接提示注入、无攻击噪声底与防御副作用（P0-3 新口径）

> 新口径要求每个注入臂并列给出：**主指标决策翻转率 (`fail→pass / base_fail`)**、**次指标归一化分差 `Δ / (max - min)`**、**传统涨分率与无攻击重复噪声底**、**有效配对数**。P1-5 事前冻结的 15 模板 held-out 攻击集（`SHA-256 = 08a07040...bab30081`）三臂全部实测已归档至上表 §2.4（`C-P15-01..05`）。

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

## 6. Track B 数据工程、原创容器题与离线测试

| ID | 指标 | 数值 (`x/n`) | 定性 | 来源 |
| :--- | :--- | :--- | :--- | :--- |
| `C-TRK-01` | 跨源统一轨迹快照（Claw-Eval + SWE-bench + τ-bench） | `87 + 8 + 825 = 920` 条标准化轨迹（其中 τ-bench 抽取 `200` 条冻结主队列） | `deterministic` | `docs/SWE_IMPORT.md`, `reports/p1_cohort_summary.json` |
| `C-TRK-02` | 原创题防刷分对照（只看末轮声明误选无产物幻觉） | `2/2` 误选无产物幻觉；可执行 Verifier `16/16` 通过并过 `TRL 0.29` | `deterministic` | `docs/TRAINING_CANDIDATES.md`, `docs/ORIGINAL_API_PILOT.md` |
| `C-ENG-01` | 离线禁网单测数量 | `537` 项（含 P0-2/P1-5 防泄漏守卫、P0-3/P0-4 统计、P1 τ-bench/多厂商/消融、`reasoning_effort`/Markdown 代码块剥离与 7 张 SVG 交付件单测） | `deterministic` | `tests/` |
| `C-COST-01` | 截至 v2 累计保守预算 guard 支出与官方 DeepSeek 复跑实扣 | v1/v2 合计 `$10.751405`（v1 `$9.180483` + v2 `$1.570922`）；P1 GLM 主实验运行于中转站并记录在本地账本；P1-4 官方 DeepSeek `deepseek-flash` post-D31 全量 400 次调用实扣 **`¥1.25` CNY**（`¥4.96 → ¥3.71`） | `deterministic` | `docs/BUDGET_v2.md`, `outputs/usage/` |

---

## 7. 已撤回口径记录（严禁作为有效结论引用）

| ID | 原表述 | 撤回原因 | 决策记录 | 替代来源 |
| :--- | :--- | :--- | :--- | :--- |
| `R-01` | v1 声称未防御 `Accuracy` 翻转率 `75% (18/24)` | 全部 24 对均来自同 1 条基线失败轨迹（`n_traj=1, n_scenario=1`），属伪重复 | `PREREG_v2.md` §6 | 降级为单轨迹 Case Study；新翻转率来自 P1-5 held-out |
| `R-02` | Stage 3 声称 `EvidenceGroundedGrader` 将注入膨胀率「压降 15 倍至 `6.25% (1/16)`」 | `grounded_judge.py` 中的 `_INJECTION_CUE_RE` 直接匹配 `perturb.py` 攻击模板并在扰动臂 `16/16` 触发（原始臂 `0/47`），构成测试集特征泄漏 | `docs/DECISIONS.md` **D30** | 仅允许引用 P1-5 事前冻结的 **held-out** 攻击集结果 |
| `R-03` | 旧报告声称 LOSO 均衡校准 `Comprehensive`「误杀 62.5% 正常轨迹」 | `generate_figures.py` 读取错误键名后触发硬编码回退，将均衡目标的漏判率 `62.5% (10/16)` 误作误杀率（实际均衡误杀率为 `5/32 = 15.6%`，`miss ≤ 25%` 目标误杀率为 `23/32 = 71.9%`） | 本表 `C-CAL-01` / `C-CAL-02` | 已修正 `generate_figures.py` 与全部报告 |
