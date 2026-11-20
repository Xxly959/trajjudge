# TrajJudge 简历与面试口径包（v3，严格对齐 `CLAIMS.md`）

> 所有数字均可在 `docs/CLAIMS.md` 与 `reports/` JSON 产物中逐一溯源；不含已撤回口径（v1 `75%`、Stage 3 `6.25%`、`62.5%` 误杀误报）与非确证探索结果（Best-of-N、P1-5 注入）；P1-3 `13/92` 疑似盲区明确标为待人工复核状态。

---

## 一、中文简历 Bullet（3 条高密度版，适配 Agent Eval / Infra 实习）

1. **证据锚定轨迹裁判与可调风险工作点**：针对多步 Agent 评测中通用裁判漏判率高且离散 Likert 分无法调节阈值的问题，基于 `Extract-Audit-Veto` 架构（确定性副作用账本 + `<untrusted_tool_data>` 隔离槽 + 证据索引与 Veto 门控）搭建离线可审计裁判；在 `200` 条 τ-bench 客观数据库真值轨迹（`131` 独立场景）上，配对 `ΔAUC` 较 OpenJudge `Comprehensive` 提升 **`+0.156`**（`0.764 vs 0.608`, `p = 0.001`；ITT 补齐失误后 **`+0.121`**, `p = 0.012`），并在 `GLM-Flash` / `DeepSeek-Flash` 双底座上将默阈失败召回推高 **`+36.9 pp / +31.6 pp`**（至 `63.7% / 48.0%`，越权精确率 `84.4% / 74.1%`），提供 46 档连续阈值（对比 `Accuracy` `{1,2,3}` 离散死区）。
2. **Pre-registered 独立验证与组件消融审计**：采用事前提交哈希锁定 `100` 条未进主队列 τ-bench 轨迹完成独立验证与冻结阈值跨分布迁移实验（`reports/p1_validation_v3.json` / `operating_points_v3.json`），严格区分“排序能力边界（受 `airline 36.5%→4%` 域漂移与 `D33 reasoning_effort` 混淆影响，`ΔAUC = -0.034`）”与“工作点可迁移性（默阈召回维持 `34.1% vs 5.1%`，需分域重标定阈值）”；`60` 条分层组件消融证实账本（`ΔAUC +0.157, p=0.012`）与隔离槽（`+0.105, p=0.015`）构成主要贡献，`3` 套等价提示词 `AUC` 均值 `0.900`（`SD = 0.009`）。
3. **上游开源贡献与评测工程基础设施**：无侵入打通 Claw-Eval 沙箱与阿里 OpenJudge，定位并修复 `raw_score` 钳制覆盖缺陷与连续分投票 `15/22 (68.2%)` 面板退化为 `min-of-3` 两处上游 Bug，合入 **[OpenJudge PR #246](https://github.com/agentscope-ai/OpenJudge/pull/246)** 与 **[PR #248](https://github.com/agentscope-ai/OpenJudge/pull/248)**（关闭 **Issue #247**）；沉淀跨源 `920` 条标准化轨迹 Schema、SHA-256 去重缓存、中转模型响应审计（`relay_audit.py`）、Socket 断网回归单测与防泄漏/防幻觉守卫。

---

## 二、English Resume Bullets (3-Bullet Version)

1. **Evidence-Grounded Trajectory Judge & Auditable Operating Points**: Designed `EvidenceGroundedGrader` (deterministic side-effect ledger, `<untrusted_tool_data>` quarantine, `[index]` citations, and Python veto gate) to replace coarse `{1, 2, 3}` generic rubrics in multi-step tool-use evaluation. On `200` objective τ-bench trajectories (`131` scenarios), it outperforms OpenJudge `Comprehensive` in paired `ΔAUC` under both complete-case (**`+0.156`**, `p = 0.001`) and error-imputed ITT (**`+0.121`**, `p = 0.012`), shifts default failure recall by **`+36.9 pp` / `+31.6 pp`** across GLM and DeepSeek backbones (`84.4% / 74.1%` unauthorized-action precision), and provides continuous threshold tuning.
2. **Pre-Registered Independent Validation & Ablation Diagnostics**: Executed a pre-registered `n = 100` out-of-sample τ-bench validation and frozen threshold transfer study, diagnosing non-replicated `ΔAUC` (`-0.034, p = 0.840`) to `airline → retail` domain shift (`36.5% → 4%`) and `reasoning_effort` confounding while confirming default operating-point separation (`34.1% vs 5.1%`) and domain-calibration needs. Paired ablation (`n = 60`) verifies significant `ΔAUC` gains from the ledger (`+0.157, p = 0.012`) and tool quarantine (`+0.105, p = 0.015`), with `0.900` mean AUC (`SD = 0.009`) across 3 prompt paraphrases.
3. **Upstream Open-Source Fixes & Reproducible Evaluation Infra**: Built a non-invasive OpenJudge bridge and reproducible runner featuring SHA-256 deduplicated caching, relay model-response auditing (`relay_audit.py`), normalized `920`-trace storage, and socket-blocked CI tests; upstreamed **[OpenJudge PR #246](https://github.com/agentscope-ai/OpenJudge/pull/246)** (`raw_score` preservation) and **[PR #248](https://github.com/agentscope-ai/OpenJudge/pull/248)** (closing **Issue #247** on `15/22` voting `min-of-3` collapse).

---

## 三、90 秒面试口头自述（统一口径）

> 「我独立做了 TrajJudge 多步 Agent 轨迹评测项目。起因是现有通用 LLM 裁判经常被助手末轮流畅话术蒙蔽，比如阿里开源 OpenJudge 的 `Comprehensive` 在 200 条客观 τ-bench 上只抓出 `4.4%` 的失败，而 `Accuracy` 也只有 `27.3%` 且 `{1,2,3}` 三分制调不动阈值。
> 我做了两件事：先是源码审计，向 OpenJudge 合入了 PR #246 和 PR #248 修复两个上游缺陷；然后设计了证据锚定裁判，按“抽取确定性账本 -> 工具输出放进隔离槽 -> `[消息编号]` 逐条审计 + Python Veto 兜底”三步走。
> 实测时我刻意用**配对 `ΔAUC` 和 ITT 失误归零**双口径做严格自检。结论非常诚实：**结构化架构没有凭空拔高模型本身的判别天花板，它的真实价值有三点：① 把近乎失效的 `Comprehensive` 显著拉到可用区间（`ΔAUC +0.156`, ITT `+0.121`）；② 在 GLM 和 DeepSeek 上把默认判定点稳定推向高召回可调区（+36.9 pp / +31.6 pp）；③ 每条判定都附带可溯源的 `[index]` 证据和越权标志，允许针对具体误杀审计和调参。** 另外我还事先Commit锁定并跑了 100 条独立验证集，实事求是诊断出了 `airline→retail` 域漂移和推理预算混杂问题。」

---

## 四、协作声明模板（简历/面试统一表述）

> 「本项目使用 AI 编程助手辅助实现；实验预设、指标与配对检验口径设计、前后端防泄漏/防幻觉守卫及全部负结果排查由作者独立设计与拍板。」

---

## 五、面试高频 6 问速查（对应 Roadmap v3 模块 F3）

| 问题 | 核心回答要点（30 秒口径） |
| :--- | :--- |
| **Q1：为什么 McNemar 召回显著提升，但和 `Accuracy` 比 `ΔAUC` 不显著？** | McNemar 只比单一默认阈值的二值召回：`Accuracy` 卡在 `3%–8%` 低误杀区，`Grounded` 处在 `26%` 高召回区；`ROC-AUC` 衡量全阈值排序力，DeepSeek-Flash 上 `ΔAUC = 0.000` 而默认召回 `+31.6 pp` 正好证明两者差异在工作点位置而非全局排序暴涨。 |
| **Q2：你的架构到底带来了什么，又没带来什么？** | **没有**凭空提升模型对疑难边界样本的排序天花板；**真正带来**的是：① 让近乎失效的 `Comprehensive` 可用（`+0.156` / `+0.121`）；② 把判定点推至高召回区并把 3 分制离散死区变成 `46` 档连续阈值；③ 输出带 `[index]` 索引和 `unauthorized_side_effect` 的可审计账本。 |
| **Q3：D31 修复是在主队列上发现的，怎么证明没过拟合？100 条独立验证集结果如何？** | ① D31 只修工程 bug（多轮 `###STOP###` 终止识别 + 取消 1.5KB 政策截断）；② 事前 `PREREG_v3 §9` Commit 1 哈希锁定 100 条未用轨迹并冻结阈值再跑：`retail → retail` 同域下 `Grounded AUC 0.677 → 0.638`、`Accuracy 0.599 → 0.597`，没有过拟合；③ 验证集上 `Grounded vs Comprehensive ΔAUC` 未复现（`-0.034`），系 `airline (36.5%→4%)` 域漂移及 `D33 reasoning_effort=low` 拉高 `Comprehensive` 推理率（`59.6%→95.7%`, 代价是 7 条截断令 ITT 仅 `0.598`）双重混杂，而默阈工作点差距仍在（`34.1% vs 5.1%`），说明部署需按领域重标定阈值。 |
| **Q4：API 报错或截断的无效轨迹怎么算？会造成幸存者偏差吗？** | 同时报告 **Complete-Case（共同有效样本）** 与 **ITT（全部样本纳入，失败/缺失赋 `score = 0.0`）**。主结论 `Grounded vs Comprehensive` 两种口径均显著；`Grounded vs Accuracy`（GLM-Flash）与 `60` 条消融因 `full-v0` 有 `7/60` D33 前截断，在 ITT 下有所衰减，已全部透明写入 `CLAIMS.md` 与报告。 |
| **Q5：为什么 `no_veto` 消融在配对 `ΔAUC` 上不显著（`+0.041, p=0.105`），还要保留 Veto？** | ① 点估计与 ITT（`+0.064, p=0.023`）均为正且 **0 API 成本**；② 连续 AUC 看重排序，Veto 的工程定位是**确定性安全护栏**，在默认阈值处把 `84.4%` 高精确率越权告警刚性否决（消融 `+7.4 pp` 召回、`+0.037 κ`）；③ 当模型自身输出「账本发现越权但 verdict 仍写 pass」的自相矛盾时，Veto 是可测试的兜底门控。 |
| **Q6：P1-3 检出的 `13/92` DB 通过疑似盲区能算最终实锤吗？** | 不能。`glm-5.3` 在此处仅作 Silver Label 初筛，仓库已提供结构化离线盲审包（`annotation/round3_review_packet/`）及 `pending_human_review` 状态报告（`reports/p13_human_review.json`）；未经过人工独立盲审前，不作为确证盲区数写进简历成果。 |
