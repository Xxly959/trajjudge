# 简历项目话术与面试应答定稿（P3，严格溯源至 `docs/CLAIMS.md`）

> **排版定位（遵循路线图 §5）**：将 `LightClaw` 作为第一主打 Agent 运行时项目；将 **TrajJudge** 定位为「`LightClaw` 配套的多步工具 Agent 轨迹元评测与质量审计子系统」，控制在 **3–4 条高密度 STAR Bullet**（所有数字与 [CLAIMS.md](CLAIMS.md) 100% 一致，零夸大、零禁用词）。

---

## 一、中文简历版（可直接复制，推荐 AI Agent / LLM Eval / 后训练数据岗位）

### TrajJudge — 多步工具调用 Agent 轨迹元评测与证据锚定裁判系统（`LightClaw` 评测子系统）
**项目定位**：面向多步工具调用 Agent 的元评测与质量审计框架，系统诊断通用 LLM-as-a-Judge 失效边界、设计证据锚定裁判架构、修复上游开源缺陷并打通多源轨迹数据管线。

- **开源审计与通用裁判失效诊断**：对主流评测框架 `OpenJudge` 做源码级审计与零改动 Transport 桥接，定位并提交修复 **2 项官方合入 PR**（[PR #246](https://github.com/agentscope-ai/OpenJudge/pull/246) 保留越界 `raw_score`；[PR #248](https://github.com/agentscope-ai/OpenJudge/pull/248) 暴露 `VotingEvaluationStrategy` 在连续分上 `15/22 (68.2%)` 面板退化为 `min-of-3` 的平局缺陷）。在 **200 条数据库可执行验证的 τ-bench 轨迹（131 独立场景）** 上定量证明通用裁判因逐步均值稀释与打分饱和造成严重漏判（`Comprehensive` 默认阈值失败召回仅 `4/91 = 4.4%`），且单纯扩大模型规模无显著收益（`Accuracy` 从 Flash 升至 Pro 召回 `27/99 → 21/100`，Exact McNemar `p = 0.167`）。
- **核心算法 `Extract-Audit-Veto` 证据锚定裁判与消融验证**：设计「确定性工具副作用账本抽取 + `<untrusted_tool_data>` 隔离槽 + 原子义务绑定与 Python Veto 一票否决」三层架构。在 200 条客观 τ-bench 队列上以 `glm-5.3-flash` 取得 **`ROC-AUC = 0.755`、`PR-AUC = 0.739`、`Recall@FPR=20% = 60.4%`、`κ = 0.380`** 全指标领先（配对 Exact McNemar 失败召回 `p < 1e-9`、总体准确率 `p ≤ 0.033`）；完成官方 `deepseek-flash` `200/200` 对称复现，将同底座默认失败召回显著提升 `+31.6 pp`（`16/98 → 47/98 = 48.0%`, `p = 7.92e-09`）并定位到零推理底座敏感性边界（`AUC 0.629`）。4 路组件消融呈严格单调阶梯（`ROC-AUC`: `full 0.910 > no_veto 0.869 > no_quarantine 0.822 > no_ledger 0.794`，`R@10%` 从 `74.1%` 递减至 `27.6%`），3 套等价提示词方差极低（`ROC-AUC` 均值 `0.900`，SD `0.0092`），且 `unauthorized_side_effect` 越权标志在 **GLM-Flash (`84.4%`, `27/32`) / GLM-Pro (`75.0%`, `30/40`) / DeepSeek-Flash (`74.1%`, `20/27`)** 上保持稳定精确率。
- **抗间接提示注入、银标盲区审计与评测边界界定**：建立带 3 次重复无攻击噪声底（`26.4%–47.6%`）与 3-gram CI 防泄漏守卫的冻结 **15 模板 Held-Out** 注入集，验证 `<untrusted_tool_data>` 隔离槽将 `tool_result` 决策翻转率控制在 **`10/134 (7.5%)`**（涨分率 `20.1%` 低于无攻击噪声底 `26.4%`，`no_quarantine` 组为 `7/55 = 12.7%`，JSON 伪装翻转由 `15.8%` 降至 `3.5%`）。同时利用跨厂商银标在 `92` 条 DB 通过轨迹中检出 **`13/92 (14.1%)`** 流程盲区，并在 Best-of-4 重排（`50` 任务）中诚实界定无执行反馈离线排序（`45.5%` vs 随机 `42.0%`，共同对齐 `n=28` 与 `Comprehensive` 同为 `57.1%`）相对 DB Oracle（`72.0%`）的 `26.5 pp` 边界。
- **多源轨迹数据工程与容器防刷分（Track B）**：设计统一 `task / trial / outcome / judgments` 四层 Schema 汇聚 **920 条标准化轨迹**（τ-bench `825` + Claw-Eval `87` + SWE-bench `8`）；构建断网容器化原创编程题与黑盒 Verifier，对照实证「只看末轮声明会 `2/2` 误选无产物幻觉」，全库配备 **537 项 Socket 断网单测**与 Fail-Closed 预算守卫。

*(如简历版面极紧，可合并后两条为 3 条 Bullet：第 1 条“诊断 + OpenJudge 2 PRs”；第 2 条“Extract-Audit-Veto + 200 条 τ-bench + 单调消融”；第 3 条“15 模板 Held-Out 注入 + 920 条多源轨迹与容器防刷分”。)*

---

## 二、English Resume Version

### TrajJudge — Trajectory Meta-Evaluation & Evidence-Grounded Audit Framework (for `LightClaw`)
- **Failure Diagnosis & Upstream Open-Source Fixes**: Audited `OpenJudge` at source level via a zero-patch `HTTPX` transport bridge and merged **2 upstream PRs** into `agentscope-ai/OpenJudge:main` ([PR #246](https://github.com/agentscope-ai/OpenJudge/pull/246) preserving unclamped `raw_score`; [PR #248](https://github.com/agentscope-ai/OpenJudge/pull/248) exposing `VotingEvaluationStrategy` tie metadata where `15/22 (68.2%)` continuous panels degenerated to `min-of-3`). Quantified generic judge failure on **200 DB-verified τ-bench traces (131 scenarios)** (`Comprehensive` default recall `4/91 = 4.4%`; scaling generic `Accuracy` Flash→Pro yielded no gain, `27/99 → 21/100`, exact McNemar `p = 0.167`).
- **Evidence-Grounded Judge (`Extract-Audit-Veto`) & Monotonic Ablation**: Built a three-stage judge combining deterministic tool-ledger extraction, `<untrusted_tool_data>` isolation slots, and obligation-bound Python veto gates. On the 200-trace τ-bench benchmark with `glm-5.3-flash`, it led across all metrics (**`ROC-AUC 0.755`**, **`PR-AUC 0.739`**, **`R@FPR=20% 60.4%`**, **`κ 0.380`**; paired McNemar `p < 1e-9` fail recall, `p ≤ 0.033` overall accuracy), and on a full 200-trace official `deepseek-flash` symmetry run it lifted failure capture by `+31.6 pp` (`16/98 → 47/98 = 48.0%`, `p = 7.92e-09`) while surfacing zero-thinking reasoning-budget sensitivity (`AUC 0.629`). Verified strict monotonic degradation across 4-way ablation (`ROC-AUC`: `full 0.910 > no_veto 0.869 > no_quarantine 0.822 > no_ledger 0.794`), low cross-prompt variance (`ROC-AUC SD = 0.0092` over 3 rewrites), and steady `unauthorized_side_effect` precision across **GLM-Flash (`27/32 = 84.4%`)**, **GLM-Pro (`30/40 = 75.0%`)**, and **DeepSeek-Flash (`20/27 = 74.1%`)**.
- **Held-Out Prompt Injection & Verification Boundaries**: Evaluated against a frozen **15-template held-out injection suite** (`SHA-256`-pinned, guarded by 3-gram leakage tests in CI) paired with an unperturbed repeat noise floor; full quarantine kept `tool_result` flip rate at **`10/134 (7.5%)`** with inflation (`20.1%`) below the `26.4%` noise floor (vs `7/55 = 12.7%` without quarantine; JSON disguise flips `3.5%` vs `15.8%`). Identified `13/92 (14.1%)` DB-pass process blind spots via cross-vendor silver-label audits and benchmarked Best-of-4 reranking (`45.5%` vs `42.0%` random, `72.0%` DB oracle).
- **Multi-Source Trajectory Engineering & Anti-Reward-Hacking**: Unified **920 trajectories** (τ-bench, Claw-Eval, SWE-bench) into a 4-tier schema, built Dockerized offline verifier tasks exposing claim-only hallucination selection (`2/2` false positives on naive text-only screening), and enforced quality with **537 socket-blocked unit tests**.

---

## 三、90 秒面试口头自述（标准版，数字 ≤ 5 个）

> “我在做 **LightClaw** 这个多步工具调用 Agent 运行时的时候，碰到一个很实际的问题：改完 Prompt 或记忆策略后，怎么可靠地判断 Agent 是真的变好了，还是在‘嘴硬没干活’或者越权操作？我接入业界常用的 OpenJudge 之后发现，通用裁判在多步长轨迹上经常因为前面查询步骤拿满分把最后一步的致命漏判稀释掉——在 200 条数据库验证的 τ-bench 上，默认阈值只抓出了 4% 多的失败，而且单纯换更大的 Pro 模型也没有统计提升。同时我还顺手定位并给 OpenJudge 官方合入了 2 个修复 PR。
>
> 所以我做了 **TrajJudge**：核心不是换提示词，而是一个 **Extract-Audit-Veto** 的三层混合裁判——先用确定性代码抽取工具调用与写操作账本并隔离 `<untrusted_tool_data>`，再强制 LLM 逐条核对用户义务并绑定证据索引，最后用 Python 规则对越权或无依据声明一票否决。最终在 200 条客观真值 τ-bench 上，这套架构把 `ROC-AUC` 从 0.628 拉到 **0.755**、同 20% 误杀率下召回拉到 **60.4%**；四路组件消融呈严格单调下降（`0.910 → 0.794`），换三套提示词标准差不到 `0.01`，在开发期完全未见的 15 类注入模板上也把 `tool_result` 翻转率压到 **7.5%**。我也用 AI 编程助手来加速工程实现，但实验预注册、统计纠偏、包括**主动撤回早期有偏样本和模板泄漏结论**，全程都是我按规范复核把关的。”

---

## 四、关于 AI 协作与自我纠错的加分话术（路线图 §5）

> “项目中代码模块和批跑脚本用 coding agent 加速开发，但我坚持**实验设计、统计口径、与结果审计全部人工复核**：开发过程中我先后三次自己抓出并公开撤回了问题——一是早期 `75%` 翻转率其实源于同一条失败轨迹的伪重复（已降级为 Case Study）；二是自研早期正则启发式直接撞上了开发期攻击短语构成特征泄漏（立即删除并写进 CI 3-gram 守卫测试，全部改用冻结的 15 模板 Held-Out 重测）；三是修复了画图脚本把 LOSO 漏判率误报成误杀率、以及 JSON 外层 Markdown 代码块导致 40 条缓存有效样本被丢弃的问题。所有公开数字都只能在唯一账本 `CLAIMS.md` 里查到出处。”

---

## 五、高频深度追问 Top 5 备忘

1. **Claw-Eval 48 条上 Grounded 为何没超过调阈值后的 Comprehensive，到了 200 条 τ-bench 却全面领先？**
   - 详见讲解卡 05：一是 48 条人工复测 `κ = 0.250` 本身噪声过大、置信区间宽达 40–60 pp；二是 **D31** 发现并修复了多轮对话终止态误杀（`###STOP###` / `transfer_to_human_agents`）与 6KB 业务政策截断 + 加入连续 `confidence_pass`；三是 τ-bench 的授权/写操作场景直接匹配 `EvidenceGrounded` 设计，同时仍把早期 48 条保留在报告附录 A 不删不改。
2. **四路消融里贡献最大的是哪一块？Veto 到底有没有用？**
   - 严格单调阶梯：**证据账本（`R@10%` 降 `46.5 pp`）> 隔离槽（降 `25.8 pp`，且在干净轨迹上也把误杀率从 `44.8%` 压到 `34.6%`）> Veto 门控（降 `14.8 pp`，在客观 τ-bench 上实际覆写模型误放过 `6/184` 与 `3/53`，而在旧 48 条离线审计上诚实汇报为 `0/109`）**。
3. **跨厂商自评偏好（Self-Preference）测得怎么样？有哪些局限？**
   - 严格按两厂商（GLM + DeepSeek）完整 `200/200` 对称范围披露：在 DeepSeek-V3.2 与 GPT-4o 50/50 考卷上，两厂商裁判均未出现放水同源轨迹的自评偏倚（`DeepSeek-Flash Grounded` 审 DeepSeek 轨迹 `AUC 0.659` / 召回 `48.0%` vs GPT-4o `0.599` / `47.9%`；`DeepSeek Accuracy` 亦为 `20.0%` vs `12.0%`），且 `unauthorized_side_effect` 精确率跨厂商稳定在 **GLM-Flash `84.4%` (`27/32`)**、**GLM-Pro `75.0%` (`30/40`)**、**DeepSeek-Flash `74.1%` (`20/27`)**。核心局限：(a) `DeepSeek-Flash (thinking=off)` 在完整 7KB 政策下判断更宽松，`AUC 0.629` 与低误杀 `R@10% 21.4%` 表现明显弱于带轻量推理的 `GLM-Flash (0.755)`，证明长政策核验需要轻量推理预算；(b) 出于预算未纳入第三家海外闭源厂商。
4. **Best-of-4 为什么和数据库 Oracle 差了 26.5 pp？P2-B LightClaw 门禁为什么没接？**
   - 无执行反馈的单轨迹排序无法可靠分辨同题 4 路试跑里细微的数据库参数错误，这也倒逼我们将「确定性规则 + 过程审计 + 可执行校验」分层设计（并在 P1-3 用银标反向发现 `13/92 = 14.1%` 数据库通过但过程越权的盲区）。LightClaw PR 门禁按当前范围暂缓，但底层接口与四层 Schema 已就绪。
5. **代码仓库中最熟的 5 个核心文件怎么讲？**
   - `llm.py`（统一缓存/重试/预算熔断 + `reasoning_effort` + `parse_json_object`）、`openjudge_bridge.py`（`HTTPX Transport` 零侵入拦截 + `repeat_id.{subcall}`）、`grounded_judge.py`（Extract-Audit-Veto + D31 多轮终止态）、`scenario_stats.py`（场景簇统计 + P0-3 噪声底 + Holm）、`taubench_adapter.py`（`reward` 零泄漏隔离适配）。
