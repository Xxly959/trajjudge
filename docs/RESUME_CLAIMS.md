# TrajJudge 简历定稿表述与证据溯源表（大厂 Agent 评测方向）

本文件每一条简历表述均经过实验数据与代码双重核验，可直接放入简历，并与你的另一个 **基于 `pi` 的 Agent 运行时项目（记忆优化 / 持久化 / 沙箱 / 提示词优化）** 形成 **「左手造 Agent Runtime，右手做 Agent 可信评测与数据闭环」** 的黄金组合。

---

## 一、 简历项目模块可直接粘贴版本（推荐 4 条核心 Bullet）

**项目名称**：**TrajJudge —— 多步工具调用 Agent 轨迹评测审计、抗注入归因与可验证数据管线**
**项目角色**：独立设计与核心研发 ｜ **代码规模**：~11,000 行 Python + **520+ 项**禁网回归单测

- **无损评测底座与确定性恢复工程**：针对多步 Agent 评测中系统提示丢失、重复采样伪命中与异常中断痛点，基于自定义 HTTPX Transport 与多进程绑定无侵入打通 Claw-Eval 沙箱与 OpenJudge；实现 HTTP Sidecar 无损恢复、`repeat_id` 子调用级内容寻址缓存、Decimal 预算熔断与行级原子 Checkpoint（实测触发 HTTP 402 欠费时零脏写安全停机并支持断点续跑），配套构建 **520+ 项**禁网单测与 GitHub Actions 自动化验证。
- **LLM-as-a-Judge 元评测、2×2 规模×架构消融与改进闭环**：基于 36 个语言无关独立场景（87 条真实沙箱轨迹、双轮引证盲标与追加式裁定审计）开展预注册研究；通过结构指纹去重与留一场景交叉验证（LOSO）揭示通用 LLM 轨迹评分器漏判 **92.9%–100%** 真实失败（强压阈值则误杀 **62.5%** 正常样本），且单纯升级 4.4 倍单价的 `deepseek-v4-pro` 模型失败召回率**零增长（7.1% → 7.1%）**；针对失败分类学归因出的“事实核验缺失”设计**工具副作用账本 + `<untrusted_tool_data>` 隔离槽 + 义务级 Veto 门控评分器**，在零隐藏规则输入下实现失败召回率 **3 倍提升（7.1% → 21.4%，Pro $\kappa$ 提升 8.8 倍）** 并将最强注入膨胀率压降 **15 倍（93.8% → 6.25%，0 次翻转）**，同时定位上游 OpenJudge 原始分钳制覆盖与 `Voting` 连续分退化为 `min-of-3`（**68.2%** 面板）两处源码缺陷并给出修复补丁。
- **间接提示注入攻防与等长中性对照归因**：设计 4 级渐进诱导 × 双注入位点的 **1,728 次**配对对抗实验，采用场景簇精确符号翻转置换检验（Holm 校正）证实工具返回注入可致最高 **89.4%** 的分数膨胀（$p_{\text{adj}}=0.0078$）；独创**事前哈希冻结的等长中性通知对照实验**，证伪“提示词长度稀释假说”（中性臂 ASR 100%，配对差 $p=0.03125$），确立指令信任层级框架的有效性并量化揭示系统提示词使结构化输出解析失败率上升 **2.4 倍**的工程代价。
- **跨源轨迹数据工程与防刷分后训练筛选**：设计 `CURRENT` 原子指针快照与 `task/trial/outcome/judgments` 四元 Schema，统一收编 Claw-Eval、固定版本 **SWE-bench Multilingual** 与 **Harbor 断网容器**原创编程题；构建 5 路黑盒验收矩阵，实证对比仅看末轮回复筛选（100% 误选无产物幻觉样本）与可执行产物核验筛选的精度差异，打通面向 **TRL（SFT/DPO）** 的高质量工具调用语料导出与评测集任务族防泄漏隔离。

---

## 二、 与你的 `pi` Agent 项目的联动叙事话术（面试破冰王牌）

当面试官问：**“我看你简历上既有做 Agent（记忆/持久化/沙箱），又有做 Agent 评测（TrajJudge），这两个项目是什么关系？”**

> **标准满分回答**：
> “我在做基于 `pi` 的 Agent 系统（做持久化、记忆压缩、沙箱隔离和提示词迭代）时，遇到了一个非常现实的工程瓶颈：**每次我改完记忆策略或系统提示词，怎么科学地证明 Agent 真的变强了，而不是在刷分？**
> 一开始我想直接接入开源的 OpenJudge 给轨迹打分，结果发现很多明明漏发通知、算错账甚至没生成产物的失败轨迹，通用 LLM Judge 全给打了满分通过。这促使我专门立项做了 `TrajJudge`：一方面把评估器本身放到显微镜下做元评测（查出了饱和漏判、`Voting` 连续分退化和工具返回注入漏洞），另一方面确立了**『可执行环境状态校验 + 结构化工具副作用门控』**的评测准则，并顺势把这套可验证评测器用在了 SFT/DPO 后训练轨迹的清洗上。这两个项目刚好构成了 **Agent 研发（Runtime）→ 可信评测（Eval）→ 数据回流（Post-Training）** 的完整飞轮。”

---

## 三、 每个简历数字的精确证据与核验命令

| 简历关键指标 | 精确数值 | 仓库内可核查文件与复算命令 |
| --- | --- | --- |
| 轨迹与独立场景规模 | 87 轨迹 / 51 任务 → **36 独立场景**；盲标 48 条 / **28 场景** | `reports/scenario_map.csv` · `scripts/build_scenario_map.py` |
| 通用评分器失败漏判率 | Accuracy 漏 `15/16` (`v2: 13/14`, 92.9%)；Comprehensive 漏 `16/16` (100%) | `reports/stage3_and_neutral_v2.json` · `reports/p2-v2.json` |
| LOSO 校准误杀代价 | Comprehensive 漏判降至 62.5% 时，正常样本误杀率 **62.5%** | `reports/phase4_calibration.json` · `scripts/phase4_analysis.py` |
| 2×2 规模×架构消融与防注入改进 | 单升 `v4-Pro` 召回 **7.1% → 7.1%（零增益）**；`Pro + Evidence-Grounded` 失败召回升 **3×（21.4%）**、较同模型原生 $\kappa$ 升 **8.8×（0.016 → 0.144）**；最强注入 ASR **93.8% → 6.25%（降 15×，0 翻转）** | `reports/pro_factorial_v2.json` · `reports/stage3_and_neutral_v2.json` · `src/trajjudge/grounded_judge.py` |
| 上游 `Voting` 退化比例 | Comprehensive **15/22 (68.2%)** 面板 `voting == min(3 draws)` | `reports/robustness_v2.json` · `contributions/openjudge/ISSUE_VOTING_MIN_DEGENERATION.md` |
| 注入膨胀与 Holm 显著性 | 1,728 次评估，4/16 变体显著，最强 `L3_notice/tool_result` ASR **89.36%** ($p_{\text{adj}}=0.0078$) | `reports/phase3_scenario.json` · `reports/v1_vs_v2_stats.md` |
| 安全声明格式失败副作用 | `defended=True` 无效率 **2.20% (19/864)** vs 未防御 **0.93% (8/864)** (**2.4×**) | `reports/robustness_v2.json` §missingness |
| Phase 5 等长中性归因 | 中性臂 ASR **100%** ($\Delta=+0.1064$) vs 安全声明 **43.75%** ($\Delta=+0.0152$)，配对 $p=\mathbf{0.03125}$ | `reports/stage3_and_neutral_v2.json` → `neutral_control` |
| 跨源快照与防刷分筛选 | 联合快照 **95 条**（Claw 87 + SWE 8）；回复筛选 **2/2 假阳性** vs Verifier 核验 **16/16 通过** | `docs/SWE_IMPORT.md` · `docs/TRAINING_CANDIDATES.md` · `docs/ORIGINAL_API_PILOT.md` |
| 禁网自动化测试规模 | **520+ passed**（Socket 全阻断 + 密钥零泄漏扫描） | `pytest -q` · `tests/test_no_secrets.py` |

---

## 四、 严禁夸大的红线清单（面试防踩坑守则）

1. **不要声称“纯靠改 Prompt 就彻底解决了轨迹评测”**：必须主动讲出你的四级阶梯发现——`Evidence-Grounded` 在零隐藏规则下把 $\kappa$ 提升了 2.8 倍，但仍低于带环境状态断言的任务专属 Rubric（$\kappa=0.440$），这恰恰证明了**语义 Judge 必须与可执行 Verifier 结合**，而不是吹嘘万能 Prompt。
2. **不要声称“已完成跨厂商自评偏差剥离”**：当前实跑模型均为 DeepSeek，若被问及 Self-Preference Bias，坦诚说明这是已识别并记录的边界，架构上只需改一行 `base_url/model` 即可跑 96 次异构对照。
3. **不要再使用 v1 已撤回的“注入翻转率 75%”**：如果提及，作为你自己发现并纠正**伪重复统计陷阱**（24 对全出自同 1 条基线失败轨迹）的亮点案例来展示你的统计严谨度！
4. **不要声称“训练出了更强的模型”**：Track B 验证的是多源轨迹清洗、防刷分筛选与 TRL 0.29 格式/分词管线接通，未执行 GPU 微调训练。
