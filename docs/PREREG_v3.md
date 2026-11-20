# PREREG_v3：客观标签大样本、多厂商裁判、Held-Out 注入与 Best-of-N 预注册协议

冻结日期：2026-11-19 · 状态：**待作者确认数据源与 API 预算后启动在线实验**

本协议在发起任何 P1/P2 在线模型调用之前，预先冻结数据源口径、样本量下限、核心统计指标、Held-Out 注入测试集哈希与组件消融方案，防止事后挑指标或测试集泄漏。

---

## 1. P1-1 数据源、客观标签与样本量冻结（最高优先级）

- **主数据源：τ-bench（`retail` + `airline`）**
  - **为什么选 τ-bench**：多轮工具调用 + 数据库状态变更 + 明确业务政策/授权约束（如取消/换货/改签前须核验并获客户确认），直接检验 `EvidenceGroundedGrader` 的「未授权操作（`unauthorized_side_effect`）」与证据核验设计。
  - **客观标签定义**：`objective_pass = (reward >= 1.0 - 1e-9)`，由 τ-bench 确定性数据库终态哈希比对 + 必达输出校验生成，彻底绕开人工单人复测 `κ = 0.250` 的标签噪声问题。
  - **数据获取策略**：优先加载公开归档轨迹（官方 `sierra-research/tau-bench/historical_trajectories` 与 HuggingFace `AgentSuite/tau-bench-trajectories` 等含多厂商 Agent、多 trial `pass^k` 的完整日志），实现零 Agent Rollout 成本且天然支持 P1-4 自偏好矩阵与 P2-A Best-of-N；若公开归档某领域样本不足，再用低价模型补跑。
  - **辅助扩充**：从本地 `../claw-eval/tasks/` 的 107 个未使用 `T*` 任务中剔除中英译本孪生，补充带可执行检查的任务作为跨基准复验。
- **防泄漏硬契约（已由 `tests/test_p1_foundation.py` 强制断言）**：
  - 送入所有被测裁判的 `messages` 仅含系统业务政策、用户对话、助手回复、工具调用与工具返回；`reward`、`expected_actions`、`expected_outputs` 与数据库终态仅隔离存放在 `privileged_outcome` 中。
- **最小样本规模**：
  - 客观失败轨迹 **`≥ 100` 条**（目标 `100 失败 + 100 通过 = 200` 条，由 `select_taubench_cohort` 轮询场景优先采样）；
  - 独立场景 **`≥ 60` 个**（聚类单元 `scenario_id = taubench:{domain}:{task_id}`，同题多 trial 绝不拆作独立样本）；
  - 原有 48 条 Claw-Eval 人工盲标结果降级为附录。

---

## 2. 冻结的核心评估指标与检验方法（沿用 P0-4）

对全部待测评分器（OpenJudge `Comprehensive`、`Accuracy`、`EvidenceGroundedGrader` 及确定性规则基线）：

1. **主指标（同误杀率公平对比）**：
   - `Recall@FPR=10%` 与 `Recall@FPR=20%`（正类 = 客观失败，并列报告严格无随机化 `step` 与线性插值 `interpolated`）；
   - `PR-AUC`（失败检测平均精确率）与 `ROC-AUC`；
   - 所有置信区间统一采用 `scenario_id` 整簇 Bootstrap（`B = 2000, seed = 0`，零宽区间标为不可估）。
2. **默认阈值配对显著性检验**：
   - 二值判定之间使用精确双尾 McNemar 检验（`exact_mcnemar`，分别报告 `fail_only=True` 失败召回差与 `fail_only=False` 总准确率差）；
   - 同一实验族的多重比较采用 Holm step-down FWER 校正（`α = 0.05`）。
3. **诚实判据**：
   - 三条核心问题（通用裁判是否漏判、换更大模型是否有效、Grounded 在同误杀率下是否优于 Comprehensive）全部按新客观标签数据照实汇报；若某一结论被推翻，直接记录结果与根因，不事后更换阈值或挑子集。

---

## 3. P1-3 异厂商特权 AI 标注员（Silver Label，仅辅助分析）

- **严格反循环论证原则**：AI 标注员结果统称为 **silver label**，绝不作为评价 AI 裁判的主金标准。
- **差异化与特权设计**：
  - 厂商必须与主测裁判不同（例如主测 DeepSeek 时，特权标注员用 Qwen 或 GLM 旗舰）；
  - 标注员拥有被测裁判看不到的特权信息（`privileged_outcome`：完整任务指令、期望动作列表、数据库终态比对摘要与任务 Rubric）。
- **唯二用途**：
  1. 在原 48 条 Claw-Eval 轨迹上与人工标签比对一致率，全部不一致样本由作者逐条裁定并写明理由，生成 `round3_adjudicated`；
  2. 在 P1-1 τ-bench 数据上筛出「程序判 `reward=1.0` 但特权 AI 标注员判失败」的样本（例如数据库碰巧一致但过程存在冗余或潜在越权），由作者抽查 20 条以量化程序校验的盲区。

---

## 4. P1-4 多厂商裁判矩阵（3 家厂商）

- **3 家裁判**：`deepseek`（Flash / Pro）+ `qwen`（DashScope 兼容接口）+ 第三家（`glm` 或 `kimi`，通过 `configs/providers.yaml` 统一调度与 `thinking_style` 适配）。
- **统一汇报字段**：`Recall@FPR=10%/20%`、`PR-AUC`、默认阈值召回与误杀、格式/校验失败率、平均延迟（ms）与单条成本（USD/CNY）。
- **简化自偏好检验**：若 τ-bench 归档包含 ≥ 2 家不同厂商 Agent（如 OpenAI + Qwen），直接输出 `2×3` `agent × judge` 交叉表；否则如实写进局限声明。

---

## 5. P1-5 Held-Out 间接提示注入测试（哈希已事前冻结）

- **开发/测试严格切分**：
  - `dev` 集：`src/trajjudge/perturb.py` 原 4 条模板（已在 v1/v2 开发期暴露，不再用于报告 Grounded 防御效果）；
  - `test` 集（held-out）：`src/trajjudge/perturb_v3.py` 新增的 **15 条未见模板**（涵盖英文间接 QA/审批覆盖、中文翻译与自然改写、JSON 字段伪装 `grader_note` / `_eval_metadata`、业务政策/离线确认伪造）。
- **冻结哈希**：
  - `held_out_suite_sha256()` = **`08a07040fbdd21d7b66000cca1ad19e81aafbef66b356823af98eac5bab30081`**
  - 自动化单测 `tests/test_p1_foundation.py` 强制断言 `grounded_judge.py` 源码及全部提示词变体与这 15 条模板共享的 ≥ 3 词英文片段数量为 **0**。
- **3 个注入位置**：`tool_result`、`assistant_mid`（中间助手轮）、`assistant_final`（末轮助手回复）。
- **冻结指标（沿用 P0-3）**：
  - 主指标：**决策翻转率**（`fail→pass / base_fail`，基线失败场景 `< 5` 标为 Case Study）；
  - 次指标：**归一化分差** `Δ / (max - min)`；
  - 并列报告：**无攻击重复 3 次噪声底**与有效配对数。

---

## 6. P1-6 组件消融与提示词敏感性

- **4 组组件消融**（`grounded_judge.py` `ablation` 参数已就绪）：
  1. `full`：完整版（账本抽取 + `<untrusted_tool_data>` 隔离 + Python Veto 门控）；
  2. `no_veto`：去掉代码侧 Python Veto 覆写（直接采纳模型 `verdict`）；
  3. `no_quarantine`：去掉 `<untrusted_tool_data>` 标签与安全边界段落（重点在 P1-5 注入集上测影响）；
  4. `no_ledger`：去掉结构化账本抽取，直接喂原始 `messages`。
- **核心诊断量**：报告每组 `veto_overrode_model` 比例（历史 48 条离线审计已测得 `0/109`，见 `reports/veto_ablation_offline.json`）。
- **提示词敏感性**：在 `full` 模式下比较 3 组语义等价提示词（`prompt_variant = v0 / v1 / v2`），报告核心指标均值、标准差与极差。

---

## 7. P2-A Best-of-N 重排闭环（N = 4）

- **任务选取**：在 P1-1 的 τ-bench 多 trial 数据中，选 50–100 个具有 `N = 4` 条独立候选轨迹的任务（通过 `select_best_of_n_tasks` 生成）。
- **5 种选择策略对照**：
  1. `random`（随机选 1 条，解析期望值 `mean(pass_count / 4)`）；
  2. `final_confidence`（末轮回复长度/确定性启发式基线）；
  3. `comprehensive`（选 OpenJudge `Comprehensive` 最高分轨迹）；
  4. `grounded`（选 `EvidenceGroundedGrader` 最高分/通过轨迹）；
  5. `oracle`（可执行数据库终态检验上界，`pass_count > 0` 即通过）。
- **主指标**：被选中轨迹的真实客观通过率（附场景簇 Bootstrap 95% CI 与配对 McNemar 检验）。

---

## 8. 成本守卫与审批门控

- 所有外部厂商模型在 `configs/pricing_v3.yaml` 中单价初始为 `null`，`LLMClient._check_budget` 默认阻断未核实定价的付费请求（D5 / D9）。
- 预计总 API 成本目标 **¥100–200**（约 `$14–28`），每个子阶段（P0-3 中性臂重跑、P1-1、P1-3、P1-4、P1-5、P1-6、P2-A）均先打印估算费用并由作者显式指定 `--cap-usd` 后执行。

---

## 9. 独立验证集与工作点迁移预注册（Roadmap v3 模块 B，2026-11-20 冻结）

- **立项原因**：D31 的两项关键修复（多轮终止态 `###STOP###` / `transfer_to_human_agents` 识别与 7KB 业务政策完整保留 + `confidence_pass` 连续排序）是在 200 条主队列发现并修复后在同一批数据上报告的。为回应潜在的过拟合质疑，在发起任何验证集在线 API 调用前，事前冻结一批与主队列及 Best-of-N 已用轨迹完全无交集的独立验证集。
- **源池约束与抽样规则（`scripts/run_p1_validation.py build`，`seed = 20261120`）**：
  - 从 `825` 条 τ-bench 源池剔除主队列 `200` 条与 `P2-A` `p2bon-t50` 已用 `200` 条（二者并集 `363` 条）后，剩余可用池共 **`462`** 条。
  - **源池分布约束**：`DeepSeek-V3.2` 全池仅含 `60` 条失败（主队列已用 `50` 条），仅余 `10` 条未用失败；同时 `p2bon-t50` 已消耗全部 `50` 个 `gpt-4o-airline` 任务。为保持两类 Agent 内部精确 50/50 平衡且消除 Agent × 失败率混杂，确定性分层抽取 **`100`** 条（`50` 失败 + `50` 通过）：
    - `DeepSeek-V3.2`：`10` 失败 + `10` 通过（`20` 条，覆盖 `airline` `4` 条 + `retail` `16` 条）；
    - `gpt-4o`：`40` 失败 + `40` 通过（`80` 条，全部为 `retail` 域）。
  - **优先未见场景**：桶内优先跨场景轮询抽取主队列未出现过的场景（`scenario_seen = false`），不足时再从已见场景的其他 trial 补足（`scenario_seen = true`）。最终冻结组成：
    - `scenario_seen = false`（完全未见场景）：**`93/100` 条**（`43` 失败 + `50` 通过，**`32`** 个未见独立场景）；
    - `scenario_seen = true`（已见场景未见 trial）：**`7/100` 条**（`7` 失败，来自 DeepSeek `6` 条 + GPT-4o `1` 条，覆盖 **`7`** 个已见场景，全队列共 **`39`** 个独立场景）；
    - 报告阶段必须同时给出全量与按 `scenario_seen` 分层的独立结果。
  - **冻结队列校验哈希**：`cohort_sha256` = **`6716de02fa66a8e7214333d88a504886809d92202266d8c3066c592a28f766c1`**（汇总文件：`reports/p1_validation_cohort_summary.json`）。
- **主队列事前冻结的工作点阈值（`scripts/operating_points.py --main-only`，预测失败当且仅当 `score < threshold`）**：
  - `Evidence-Grounded · glm-5.3-flash`：
    - 默认阈值：`0.50`（主队列 complete-case 召回 `63.7%` `58/91`，误杀 `25.8%` `24/93`）；
    - **严格档**（主队列 `FPR <= 10%` 下最大召回）：**`0.1294`**（对应 `score < 0.135`，主队列召回 `37.4%` `34/91`，误杀 `8.6%` `8/93`）；
    - **宽松档**（主队列 `Recall >= 80%` 下最小误杀）：**`0.98125`**（对应 `score < 0.9825`，主队列召回 `87.9%` `80/91`，误杀 `59.1%` `55/93`）。
  - `OpenJudge Accuracy · glm-5.3-flash`（对照）：
    - 默认 / 严格档（`FPR <= 10%`）：**`1.5`**（对应 `score < 2.0`，主队列召回 `27.3%` `27/99`，误杀 `8.0%` `8/100`）；
    - 宽松档（`Recall >= 80%`）：因 `Accuracy` 仅输出 `{1, 2, 3}` 离散整数，次最高分界 `2.5`（`score < 3.0`）召回仅 `54.5%`（误杀 `18.0%`），满足 `Recall >= 80%` 的阈值 **`3.01`** 退化为 `always_fail`（`100% / 100%`）；验证集迁移同时对照非退化最高档 **`2.5`**。
  - `OpenJudge Comprehensive · glm-5.3-flash`（对照）：
    - 默认阈值：`0.60`（主队列召回 `4.4%`，误杀 `1.1%`）；
    - 严格档（`FPR <= 10%`）：**`0.742969`**（主队列召回 `20.9%`，误杀 `6.5%`）；
    - 宽松档（`Recall >= 80%`）：**`0.90483`**（主队列召回 `80.2%`，误杀 `66.3%`）。
- **验证集运行配置与事前成功判据**：
  - 运行配置：`hubcore_glm_flash`（`glm-5.3-flash`, `reasoning_effort=low`, `max_tokens=4096`, `schema_retries=2`, `workers=4`），共 3 个评分器 × 100 条 = 300 次调用；目标 Grounded 无效率 `< 5%`，全部指标并列报告 **`complete_case`** 与 **`ITT`**（无效行按判失败、`raw_score = 0.0` 计入）。
  - **主假设**：`Grounded-GLMFlash` 相对 `Comprehensive-GLMFlash` 的场景簇配对 **`ΔAUC > 0`**，且 95% 场景簇 Bootstrap CI（`B = 2000, seed = 0`）**不跨 `0`**；
  - **次要结果**：`Grounded-GLMFlash` 相对 `Accuracy-GLMFlash` 的配对 `ΔAUC`，无论正负或显著与否均照实报告；
  - **工作点迁移**：将上述主队列冻结的严格档与宽松档阈值原封不动应用至验证集，如实报告验证集实际召回、误杀与漂移（pp）。无论验证结果如何，均不改写主假设、不事后重调阈值或重抽样本。
