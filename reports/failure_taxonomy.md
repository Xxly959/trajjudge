# Phase 4 — 失败分类学（硬样本子集，PROVISIONAL / exploratory）

> **PROVISIONAL**：依赖 round1 人工标签，**闸门 A 未通过**。按 PREREG_v2 §7/§7b 全部标 **exploratory**，
> 不得写入 `FINAL_REPORT_v2.md` 或 `RESUME_CLAIMS.md`。若人类 test-retest κ < 0.60，永久降级为 exploratory。
>
> **传播边界（owner 约束 ①）**：本文件与评分器原话**只存在于 `reports/`**。round2 完成前不得进入
> `annotation/GUIDE.md`、盲标 kit、任何标注视图或 `docs/` 交付物。
>
> **judgment 约定**：每条分类都是**助手（agent）的判断**，不是人工标签、不是评分器输出、不是上游结论。
> 每条都显式标 `judgment: agent`。分类词表在 PREREG_v2 §7b **事前冻结**（7 类），未在看到结果后增删。
>
> **隐私约定**：正文只用**盲 ID**（`B` + 6 hex）。`trace_id`、任务路径、人工理由**原文**只留在本地
> `reports/phase4_hard_samples.json`（已 gitignore）与 `annotation/labels.csv`（已 gitignore）。
> 下文「人工异议要点」是**转述**，不是逐字引用。

## 1. 子集定义与分布

定义（§7 冻结）：`human fail ∧ framework passed ∧ trajectory_accuracy ≥ 2.0 ∧ trajectory_comprehensive ≥ 0.6`。
即**人工判失败、但可执行检查与两个 LLM 评分器全部判通过**的轨迹——饱和的正面证据。

- **n_traj = 10，n_scenario = 7**（≥5，故不是 case study；但 7 个场景仍属小样本）。
- 场景：competitive_intelligence, complaint_investigation, month_end_reconciliation,
  onsite_support_dispatch, order_profit_analysis, pinbench_apm_market_research, vip_ticket_escalation。
- 10 条中 **9 条 accuracy = 3.0（顶格）**，1 条 = 2.0；comprehensive 0.7031–0.9500，**全部 ≥ 0.6 过阈**。
- 原始输出恢复：**20/20 面板全部通过 token 总数 + 复算分数双重身份校验**（§7b 规则 5），
  无「原始输出不可得」条目。comprehensive 的原始输出只含 `step_evaluations`（无顶层 `reason`），
  故其原话摘录取**逐步骤 `step_reason`**，并注明步骤序号。

| 类别（冻结词表） | n_traj | n_scenario | 盲 ID |
| --- | ---: | ---: | --- |
| `missing_evidence_check` | 5 | 3 | B02eb42, B235746, B0803be, B0a3fbd, Baf6099 |
| `annotation_disagreement` | 2 | 2 | B78c979, Bed2fd2 |
| `rubric_mismatch` | 1 | 1 | Ba3a1b5 |
| `other`（理由过短，无法定位） | 2 | 2 | B9d18f3, B869dc7 |
| `surface_fluency` | 0 | 0 | — |
| `partial_credit` | 0 | 0 | — |
| `threshold_saturation` | 0 | 0 | — |

**为什么 `threshold_saturation` 是 0 条**：饱和是**子集的入选条件**（两个分数都顶格/过阈），
不是这 10 条各自的失败成因。把「分数顶格」再当成每条的失败类别会重复计数、掩盖真实成因。
饱和在本项目里是**背景事实**（v1 accuracy 顶格率 92.07%、comprehensive 最低 0.6354），
其后果由 `reports/phase4_provisional.md` §3 的校准结果承担，不由本分类学承担。

## 2. 中心模式（5/10，跨 3 个独立场景）

**评分器奖励「信息收集齐全 + 叙述完整 + 步骤连贯」，但不核对 rubric 明确要求的通知对象集合与行动项归属。**

4 条派遣/升级类轨迹（onsite_support_dispatch ×2、vip_ticket_escalation ×2）的缺陷完全同型：
**rubric 列出的必通知人里，有一人从未成为任何草稿的收件人**。两个评分器都在原话里**逐一枚举了收件人**，
枚举结果恰好漏掉那个人，然后判定「完整达成」。

更值得注意的是**扣分去向**：这 4 条里 accuracy 给 2.0 的那条（B235746）与 comprehensive 末步扣分的那条（B0a3fbd），
扣分理由都是**冗余搜索 / 重复保存草稿**，即效率问题；**实质性的通知对象遗漏一次都没有被扣分**。

第 5 条（Baf6099，complaint_investigation）是同一机制的另一种表现：rubric 要求逐案给出
「责任人 + 对客时间承诺 + 机制改进」，最终总结只覆盖了 1/3 个案例的行动项，其余两案只有「建议立即打款」
「建议立即恢复功能并致歉」这类无责任人、无时限的短语；评分器原话仍称
「writes detailed investigation conclusions and handling recommendations for each case」。

**这个模式是可执行检查能覆盖的**：必通知人集合、草稿收件人集合、逐案行动项是否含责任人与时限，
都是从轨迹结构化字段可直接判定的谓词，不需要语义判断。这正是 §5「混合评分」支持证据的机制解释。

## 3. 逐轨迹条目

以下每条的证据编号 `[N]` 与标注视图同源：`adapt_trace(...).messages` 的 **0-based** 下标。
摘录为**逐字引用**（截断处以 `…` 标明），可在本地 `reports/phase4_hard_samples.json` 的
`evidence[N].excerpt` 与 `graders.*.raw` 中核对。

---

### B02eb42 — onsite_support_dispatch

- 分数：accuracy **3.0**，comprehensive **0.7361**；framework **passed**；human **fail**。
- 类别：`missing_evidence_check`
- `judgment: agent`

**人工异议要点（转述）**：所选工程师的到场时间口径不对（客户要求的到场时刻更严），且草稿未发给技术总监。

**轨迹证据**：
- rubric（criteria）明确要求通知两人：`Zhao Lei (Account Manager)` **与** `Wang Ming (Technical Director): VIP customer critical ticket requires escalation notification`；并写明客户邮件 `msg_1201` `requiring arrival by 2:00 PM`。
- `[24]` tool：确实查到了 Wang Ming（`CT-1206`, `wangming@company.com`, Technical Director）——**信息已获取**。
- `[35]` tool：`"status": "draft_saved", "draft": {"to": "maqiang@company.com", …}`
- `[36]` tool：`"status": "draft_saved", "draft": {"to": "zhaolei@company.com", …}`
- **全轨迹只有这两封草稿，Wang Ming 从未成为收件人。**
- `[34]` assistant：`✅ **Best fit** — free from 12:00, can reach site well within 4h SLA (deadline 14:15)`
- `[37]` assistant：`…he's free from 12:00 — leaving comfortable margin to reach Shanghai Pudong before the 14:15 SLA d…`
  → 以 **SLA 14:15** 为约束，而客户邮件要求 **14:00** 前到场；更严的那个约束未被采用。

**评分器原话摘录**：
- accuracy（3.0）：`…correctly selected Ma Qiang (best skills match, available after 12:00, SLA deadline 14:15), and drafted both notification emails (engineer and account manager). The trajectory is logically coherent, goal-directed, and efficient.`
  → 评分器**自己枚举的收件人集合就是错的**（只有 engineer + account manager），并**背书了 14:15**。
- comprehensive（0.7361，末步 `[8]`）：`Saving the two drafted emails (to the engineer and the account manager) fulfills requirement 4. Content is accurate, includes incident summary, SLA, contact details, schedule note, and appropriate AM guidance.`
  → 同样把「两封」当作满足要求。

**判读（agent）**：缺陷可验证、可执行检查覆盖（收件人集合 ⊇ 必通知人集合；到场约束取 min(SLA, 客户要求)）。
**一处必须如实说明的反向事实**：rubric 写 `free from 13:00 PM onwards`，而日历 fixture `[30]`/`[31]` 显示
`System Architecture Review` 的 `"end_time": "2026-03-26T12:00:00+08:00"`。因此 agent 的「free from 12:00」**与 fixture 一致**，
是 **rubric 与 fixture 之间的口径分歧**，我不把它算作 agent 的错误，也不把它算作评分器的错误。
人工异议中「时间不对」的**可验证部分**是 14:15 vs 14:00，不是 12:00 vs 13:00。

---

### B235746 — onsite_support_dispatch

- 分数：accuracy **2.0**，comprehensive **0.7031**；framework **passed**；human **fail**。
- 类别：`missing_evidence_check`
- `judgment: agent`

**人工异议要点（转述）**：未向技术总监发出升级通知。

**轨迹证据**：
- rubric「需要通知的人」列出两人：`- 赵蕾（客户经理）：万通物流的对接人，需告知派遣安排`
  与 `- 王明（技术总监）：VIP客户critical工单需升级通知`；
  场景背景写明客户邮件 `要求下午2点前到场`。
- `[12]` tool：查到王明（`CT-1206`，技术总监，notes 明写 `VIP客户critical工单需升级通知`）。
- `[36]` tool：`"to": "maqiang@company.com"`，subject `【紧急派单】TK-1201 万通物流生产系统宕机 — 需今日现场支持（SLA 14:15）`
- `[37]` tool：`"to": "zhaolei@company.com"`
- 王明在正文里只作为**升级联系人被提及**：`[36]` `重大风险请同步技术总监王明（13800121006）`、
  `[37]` `技术总监王明（13800121006）为升级联系人`。**提及 ≠ 通知；两封草稿的收件人里没有他。**

**评分器原话摘录**：
- accuracy（2.0）：`…drafts both notification emails (to the engineer and to the customer manager 赵蕾). Information flows logically and the final summary is coherent. However, there are noticeable unnecessary steps: numerous redundant contacts_search calls … This fits a score of 2 (achieves goal with obvious unnecessary steps)…`
  → **2.0 的扣分全部来自冗余搜索**；收件人集合漏掉王明未被提及，且明写 `the task is still completed correctly`。
- comprehensive（0.7031，末步 `[11]`）：`Saving two email drafts to the engineer and account manager fulfills the drafting requirement comprehensively with accurate scheduling, SLA and escalation details. Accurate and complete.`

**判读（agent）**：与 B02eb42 同型（译本孪生，同一场景）。此条是**「扣分去向」最干净的证据**：
评分器确实扣了分，但扣的是效率，不是实质遗漏——所以「分数不是顶格」并不等于「评分器发现了问题」。

---

### B0803be — vip_ticket_escalation

- 分数：accuracy **3.0**，comprehensive **0.8625**；framework **passed**；human **fail**。
- 类别：`missing_evidence_check`
- `judgment: agent`

**人工异议要点（转述）**：遗漏了内部大客户经理，未向其同步内部升级通知与服务时限。

**轨迹证据**：
- rubric 第 3 步：`找到赵蕾（CT-1404，大客户经理）— 作为VIP客户对接人，需同步通知`；
  第 4 步：`2. **内部升级通知**（给技术总监王明+客户经理赵蕾）`。
- `[18]` tool：`"to": "maqiang@company.com; wangming@company.com"`（内部升级通知）
- `[19]` tool：`"to": "zhao@wantong-logistics.com"`（客户回复）
- **`赵蕾` 在全轨迹所有消息中出现 0 次**（逐消息全文计数）。
- **易混淆点必须点明**：`zhao@wantong-logistics.com` 是**客户方的赵总监**（rubric 场景背景中的投诉人），
  与**内部的客户经理赵蕾**是两个不同的人。草稿发给了前者，不能算通知了后者。

**评分器原话摘录**：
- accuracy（3.0）：`…finds the appropriate technical leads (DBA 马强 and 技术总监 王明), updates the ticket to P0 and assigns it, and drafts both the internal escalation email and the customer reply. All steps are coherent, progressive, and efficient with no unrelated actions.`
  → 「appropriate technical leads」只列两人，**赵蕾不在评分器的世界里**。
- comprehensive（0.8625，末步 `[4]`）：`…saves two well-crafted drafts (internal notification to DBA+技术总监, and customer reply to 赵总监). This directly fulfills step 4 and the whole escalation workflow. Highly relevant, accurate, and efficient.`
  → 逐字确认收件人是 DBA+技术总监 与 赵总监，仍判 `directly fulfills step 4`。
- 维度均值（5 步）：contribution 4.2 / relevance 4.6 / **accuracy 4.8** / efficiency 4.2。

**判读（agent）**：这是本子集里**证据最硬的一条**—— required-notify 集合缺员，且缺失者在轨迹中零出现，
两个评分器的原话都自证了其枚举不完整。可执行检查（收件人集合比对 + 必通知人是否被检索到）可直接判定。

---

### B0a3fbd — vip_ticket_escalation

- 分数：accuracy **3.0**，comprehensive **0.7656**；framework **passed**；human **fail**。
- 类别：`missing_evidence_check`
- `judgment: agent`

**人工异议要点（转述）**：遗漏客户经理赵蕾。

**轨迹证据**（与 B0803be 同场景、同 rubric，不同轨迹）：
- `[19]` tool：`"to": "wangming@company.com, maqiang@company.com"`
- `[20]` / `[22]` tool：`"to": "zhao@wantong-logistics.com"`（客户回复被**重复保存两次**）
- `[23]` assistant（「技术负责人」小节只列两人）：
  `- **马强｜高级 DBA**（技术部，北京分部，maqiang@company.com）— 主责工程师，负责数据库相关故障排查`、
  `- **王明｜技术总监**（上海总部，wangming@company.com）— 知识库指定的 **P0/P1 升级接收人**，负责跨部门协调`。
- **`赵蕾` 在全轨迹所有消息中出现 0 次。**

**评分器原话摘录**：
- accuracy（3.0）：`轨迹完整覆盖了用户的四个任务要求：查看工单与CRM信息、知识库搜索方案、找到技术负责人（马强DBA+王明技术总监）、起草内部通知与客户回复两封草稿，并相应更新了工单。…存在少量低效之处：重复搜索了相同知识库关键词、初次通讯录查询为空后重新查询，以及将客户回复草稿重复保存了两次（第二次为冗余重复操作），但这些均不偏离任务目标，属于可接受的轻微冗余。`
- comprehensive（0.7656，末步 `[7]`）：`重新保存了一封与第6步几乎完全相同的客户回复草稿（仅去掉了末尾一句标注），属于完全重复的冗余操作，未增加任何价值。`
  → **comprehensive 的末步扣分针对重复保存**，不是针对赵蕾缺席。

**判读（agent）**：与 B0803be 构成**同场景两条独立轨迹的同型失败**，说明这不是单次抽样噪声。
同时与 B235746 一起构成「扣分去向 = 效率而非实质遗漏」的第二、第三个实例。

---

### Baf6099 — complaint_investigation

- 分数：accuracy **3.0**，comprehensive **0.7361**；framework **passed**；human **fail**。
- 类别：`missing_evidence_check`
- `judgment: agent`

**人工异议要点（转述）**：行动规划不清晰。

**轨迹证据**：
- rubric 逐案要求：案例 2 `联系财务部刘洋催促执行，给客户明确时间承诺`；
  案例 3 `联系技术部马强恢复功能，改进自动通知机制`。
- 最终 assistant 消息 `[40]` **仅 667 字符**，是三案总结：
  - 案例 2：`5 万元补偿单 TXN-604 已审批但状态为"待执行"，卡在财务环节。建议立即打款。`
    → **无责任人、无对客时间承诺**。
  - 案例 3：`建议立即恢复功能并致歉。`
    → **未指派马强、未提「改进自动通知机制」**。
  - `**建议下一步：** 中和集团案例需财务刘洋尽快确认加购模块凭证…需要我帮您把另外两个案例的回复邮件也起草出来吗？`
    → 行动项只覆盖 **1/3** 个案例，其余以反问收尾。
  - `马强` 在 `[40]` 中只出现在**通用通讯录列表**（`技术运维主管 马强 13900601003（故障报告）`），
    **不是案例 3 的指派责任人**。

**评分器原话摘录**：
- accuracy（3.0）：`…writes detailed investigation conclusions and handling recommendations for each case with a priority ranking, and drafts a reply email for the most urgent case (中和集团). The sequence is logically coherent, progression is clear…`
  → 声称 `for each case` 都有 handling recommendations，与 `[40]` 的实际内容不符。
- comprehensive（0.7361，末步 `[8]`）：`Drafted a reply email for the most urgent case (中和集团), fulfilling the final requirement. Content is appropriate and accurate.`

**判读（agent）**：与通知对象遗漏同机制——**rubric 的逐案结构化要求未被逐项核对**。
可执行检查形式：对每个案例检查行动项是否含 {责任人, 时限} 二元组。
**诚实边界**：人工理由只有「行动规划不清晰」6 字，我定位到的是**可验证的 rubric 缺项**，
不能断言这与人工所指的「不清晰」完全是同一件事；归类依据是缺项本身可验证，而非理由文本。

---

### B78c979 — competitive_intelligence ⚠️ 金标准完整性疑点

- 分数：accuracy **3.0**，comprehensive **0.9500**（本子集最高）；framework **passed**；human **fail**。
- 类别：`annotation_disagreement`
- `judgment: agent`

**人工异议要点（转述）**：认为轨迹未识别竞品 B 的 C 轮 5 亿元融资与东南亚扩张计划，未更新知识库中「海外拓展受限」的旧判断。

**轨迹证据（与异议直接矛盾）**：
- `[17]` / `[18]` tool：RSS-404、RSS-405 **已被检索并读取**（融资与东南亚计划的来源）。
- `[23]` assistant（报告草稿正文）：`完成C轮5亿元融资，红杉中国领投`；
  `融资后迅速宣布进军东南亚，新加坡设亚太总部，年底前覆盖5个东南亚国家`；
  并写明旧判断 `的判断已被推翻`（该消息为 JSON 草稿体，「海外拓展受限」在原文件中带转义引号）。
- `[24]` assistant（最终交付）：`KB-802（2026-01）称竞品B"海外拓展受限" → **已被推翻**`，
  并给出建议 `更新KB-801/KB-802`。
- rubric 要求的正是这两项更新。

**评分器原话摘录**：
- accuracy（3.0）：`…synthesizes them into a well-structured competitive intelligence report covering Competitor A (new version + AI threat) and Competitor B (funding + overseas expansion) plus impact/recommendations…All five task requirements are met with no unrelated steps.`
  → 评分器**明确把 funding + overseas expansion 记为已覆盖**，与人工异议正面冲突。
- comprehensive（0.9500，末步 `[4]`）：`Saves the email draft (not sending) as explicitly required. The draft summarizes the report accurately and includes the timeliness warning.`
- 维度均值（5 步）：contribution 4.8 / relevance 4.8 / **accuracy 5.0** / efficiency 4.6。

**判读（agent）**：异议中「**没看出**」这一半**被轨迹文本直接否证**——两处消息逐字写出了融资额与东南亚计划，
并显式标注旧判断已被推翻。「**更新**」这一半**存在合理争辩空间**：轨迹是**建议更新** KB-801/KB-802，
而非**执行**了 KB 写入；若人工的判定标准是「必须落库」，则 fail 可成立，但理由的前半句仍与证据不符。

**必须停下、不得自行处理**：
- 我**没有**修改、也**不会**修改这条标签（硬约束：不得替人工标注）。
- 这条轨迹是 **Phase 3 注入实验 16 条 human fail 候选之一**，因此该疑点**同时影响 Phase 3 的 PROVISIONAL 结果**。
- 需要 owner 裁定：理由前半句是否为笔误 / 判定标准是否为「必须执行 KB 写入」。**在裁定前，本条按原标签 fail 参与全部统计。**

---

### Bed2fd2 — pinbench_apm_market_research ⚠️ 金标准完整性疑点

- 分数：accuracy **3.0**，comprehensive **0.9375**；framework **passed**；human **fail**。
- 类别：`annotation_disagreement`
- `judgment: agent`

**人工异议要点（转述）**：理由指向「培训需求」与「干扰工单」。

**轨迹证据（理由与本条目不匹配）**：
- 本条目的 rubric 全文只有一句：
  `Reward a strategic market analysis that covers at least five APM vendors, pricing approaches, and current trends such as OpenTelemetry and AI-driven observability.`
  → **不涉及工单、不涉及培训、不涉及干扰项识别**。
- 全轨迹所有消息中 `培训` 出现 **0** 次、`training`（不区分大小写）出现 **0** 次。
- 本任务属 APM 市场研究族；「干扰工单」是 onsite_support_dispatch 族（T155zh/T156）的场景元素。
- 盲 ID → trace 映射已**独立复核**：`outputs/annotation/key.json` 反查得到的 trace_id 与
  `phase4_hard_samples.json` 记录**一致**（10/10 `map_ok=True`），故不是我的映射错误。

**评分器原话摘录**：
- accuracy（3.0）：`…It successfully fulfills all requirements: at least five competitors (Datadog, New Relic, Dynatrace, Grafana Labs, Splunk), their differentiators, pricing models, key market trends, a comparison table, and an executive summary. No unrelated or unnecessary steps…`
- comprehensive（0.9375，末步 `[2]`）：`Writing the complete, well-structured markdown analysis (exec summary, comparison table, competitor profiles, pricing patterns, trends) fulfills the deliverable and saves it to file.`

**判读（agent）**：**理由文本无法在本条目上被验证**——它描述的对象（培训需求、干扰工单）在本轨迹与本 rubric 中都不存在。
两种可能，都需 owner 判断：①理由写串了条目（笔记错位）；②理由指向我看不到的判定依据。
我**不主张**标签本身错误：fail 可能出于其他未写明的原因。

**必须停下、不得自行处理**：标签保持原样；不猜测、不补写理由、不改判。
需要 owner 在 round2 澄清本条的判定依据。**这条与 B78c979 合计占硬样本子集的 2/10（20%）**，
是本轮对金标准可靠性的**实质性负面发现**，与 Phase 2 的 62 条理由质量警告方向一致。

---

### Ba3a1b5 — order_profit_analysis

- 分数：accuracy **3.0**，comprehensive **0.8000**；framework **passed**；human **fail**。
- 类别：`rubric_mismatch`
- `judgment: agent`

**人工异议要点（转述）**：指向最终呈现/表述不清（理由原文疑有笔误，语义按「显示/表述不清」读）。

**轨迹证据（rubric 侧，可验证）**：
- 本条 rubric 全文 697 字符，内容**全部是数值**：4 个客户的成本/售价/利润/利润率、
  2 个收款异常（瀚海欠款 30k、万通退款 20k）。
- 评分档位：`0.8-1.0: 4个客户利润率正确，2个收款异常标注`；`0.5-0.7: 大部分计算正确，发现至少1个异常`；
  `0.2-0.4: 计算有误或遗漏异常`；`0.0-0.1: 未完成分析`。
- 在 rubric 全文中检索 `清晰|明确|清楚|clarity|clear|actionable|可读`：**命中 0**。
  → **rubric 没有任何呈现质量/清晰度维度**。

**评分器原话摘录**：
- accuracy（3.0）：`轨迹按顺序从 CRM、库存、财务收集数据，计算利润率，标注付款异常，并生成了全面的报告。步骤逻辑清晰、高效（并行调用，未获取无关数据）。此外还因售价与标价不匹配、退款金额可疑而标注了数据质量问题，这增强了任务效果。达成了所有目标，且没有无关步骤。`
- comprehensive（0.8000，末步 `[4]`）：`Writes the comprehensive final report to disk, covering all six requested items including anomaly flagging and data-quality caveats. Critical deliverable generation; well-structured and accurate, though slightly verbose.`
  → 唯一接近呈现质量的措辞是 `slightly verbose`，且**未导致降档**。

**判读（agent）**：人工按**呈现清晰度**扣分，而 rubric 与两个评分器都只度量**计算正确性与异常发现**。
这不是评分器算错，而是**人工判据与 rubric 判据不同维度**——`rubric_mismatch` 的定义即此。
**诚实边界**：理由原文只有 6 字且疑有笔误，我把它读作呈现质量异议；若 owner 澄清后指向别的维度，本条类别应改。
在澄清前，本条**不宜**作为「评分器漏判」的证据使用。

---

### B9d18f3 — complaint_investigation

- 分数：accuracy **3.0**，comprehensive **0.9062**；framework **passed**；human **fail**。
- 类别：`other`（理由过短，无法定位到具体缺陷）
- `judgment: agent`

**人工异议要点（转述）**：理由为「不明确」一类的极短表述，未指明对象。

**我实际核查了什么（如实记录，含反向证据）**：
- 最终 assistant 消息 `[32]`（1423 字符）**逐案给出了责任人与时限**：
  - 案例 1：`① 48 小时内书面响应…② 3 个工作日内调取加购业务依据…④ 赵蕾 + 陈萍上门`
  - 案例 2：`本周内执行 5 万付款并回传回单；陈萍致电致歉说明延误原因`
  - 案例 3：`立即恢复功能并书面确认生效时间…推动“降级前 3 天预告 + 当日通知 + 补缴自动恢复”的通知链路`
    → rubric 要求的「改进自动通知机制」**在此条中确实存在**。
  - 对客时间承诺：`承诺 11 月 5 日 18:00 前给书面核查结论 + 若举证不能 5 个工作日内全额退款`
- 也就是说：**与 Baf6099 不同，本条的可验证 rubric 要求基本齐备**。我找不到可定位的实质缺项。

**评分器原话摘录**：
- accuracy（3.0）：`…wrote per-case investigation conclusions plus handling suggestions, and finally drafted a reply email for the most urgent case (中和集团, P0). Every tool call directly supported one of the five requested tasks…The final report and draft satisfy the user's goal.`
- comprehensive（0.9062，末步 `[7]`）：`撰写完整调查报告，汇总三案核实结论、优先级、处理建议及待决策事项，形成结构化交付物，是对用户核心需求的完整落地。`

**判读（agent）**：归 `other`，**不归 `annotation_disagreement`**。
理由：**「我找不到缺陷」不等于「标签错了」**。人工可能按更严的表述标准或我未捕捉的维度判定，
而 2 字理由不足以让我定位。把它升级为标注错误会是**用我的判断覆盖人工标签**，违反硬约束。
需要 owner 在 round2 用 `[N]` 引用指明具体位置。**本条不作为评分器漏判的证据。**

---

### B869dc7 — month_end_reconciliation

- 分数：accuracy **3.0**，comprehensive **0.9062**；framework **passed**；human **fail**。
- 类别：`other`（理由过短，无法定位到具体缺陷）
- `judgment: agent`

**人工异议要点（转述）**：信息反馈不明确。

**我实际核查了什么**：
- 本条 rubric 的**最高档明确要求清晰度**：`0.9-1.0: All 3 anomaly types found, root cause chain (JOB-1301->INT-1303) accurately identified, report complete and clear`。
  → 因此**不能**归 `rubric_mismatch`：清晰度**在** rubric 内，人工判据与 rubric 同维度。
- 一条**值得记录的机制线索**（不是缺陷认定）：comprehensive 末步原话显示轨迹中**曾出现表述缺陷并被 agent 自修**，
  而评分器把这次自修记为**正向贡献**。人工可能 penalize 最终产物的清晰度，评分器则奖励「发现并修好」的过程。
  这两种口径可以同时对同一条轨迹给出相反评价。**我未据此认定人工理由成立或不成立。**

**评分器原话摘录**：
- accuracy（3.0）：`…cross-checks financial transactions against CRM receivables (correctly finding the ¥85,000 duplicate and ¥30,000 shortfall), reconciles procurement against inventory (¥7,000 overpayment, SSD no-sale, ITEM-1308 mismatch), and produces a comprehensive report with an anomaly register and prioritized actions.`
- comprehensive（0.9062，末步 `[5]`）：`Targeted edit that repairs the garbled exposure sentence from the prior step, replacing it with a clean component-by-component table separating confirmed (141,750) from provisional (inventory 41,125) exposure. This corrects a genuine accuracy defect in the key financial summary, improving the report's reliability.`

**判读（agent）**：归 `other`。6 字理由不足以定位「哪一处反馈不明确」，
而 rubric 要求的三类异常与根因链在评分器原话中都被逐项确认。**不主张标注错误，不作为漏判证据。**
需要 owner 在 round2 用 `[N]` 引用指明位置。

---

## 4. 两条金标准疑点的处置（需 owner 裁定，助手不得代做）

| 盲 ID | 场景 | 疑点性质 | 助手已做 | 助手**未**做 | 需 owner |
| --- | --- | --- | --- | --- | --- |
| B78c979 | competitive_intelligence | 理由前半句被 `[23]`/`[24]` 逐字否证；后半句（建议 vs 执行 KB 更新）可争辩 | 保留原标签 fail；标 `annotation_disagreement`；记录矛盾证据 | 未改标签、未改理由、未剔除 | 裁定判定标准是「识别并指出」还是「必须执行 KB 写入」 |
| Bed2fd2 | pinbench_apm_market_research | 理由对象（培训需求/干扰工单）在本轨迹与本 rubric 中均不存在（0 次命中） | 保留原标签 fail；复核盲 ID 映射 10/10 一致 | 未改标签、未猜测理由、未改判 | 澄清本条判定依据，或确认理由是否写串条目 |

**影响范围**：B78c979 属于 Phase 3 注入实验的 16 条 human fail 候选池，故该疑点**同时影响 Phase 3 的 PROVISIONAL 数字**。
两条合计占硬样本子集 **2/10**。在 owner 裁定前，**全部统计按原标签计算，不做任何剔除或改判**；
本轮所有数字因此都带「金标准含 2 条待裁定疑点」这一限制。

## 5. 对「可执行检查 + LLM judge 混合评分」的含义

`reports/phase4_provisional.md` §5 的判读是**有支持证据**（framework 抓 5、accuracy 抓 1、comprehensive 抓 0，
漏判集合不重合，并集漏判率 0.6250 < framework 单独 0.6875）。本分类学给出**机制解释**：

- 5 条 `missing_evidence_check` 的缺陷都是**集合/结构谓词**：必通知人 ⊆ 草稿收件人、逐案行动项含 {责任人, 时限}。
  这类谓词**可执行、无需语义判断**，正是 framework rubric 的强项、LLM 评分器的盲区。
- 两个评分器的原话**自证**了盲区：它们枚举收件人时漏人（B02eb42/B235746/B0803be/B0a3fbd），
  或声称逐案建议齐备而实际只有 1/3（Baf6099）。
- **效应量必须按条数说**：并集比 framework 单独多抓 **1 条**轨迹（6 vs 5），不是「提升 6.25 个百分点」这种
  在小样本上无意义的表述。n_scenario = 11，仍属小样本。

**反对方向的诚实记录**：10 条硬样本里有 **2 条金标准疑点 + 2 条无法定位 + 1 条判据维度不同**，
即 **5/10 不能干净地算作「评分器漏判」**。真正可验证的评分器漏判是 **5 条 / 3 个场景**。
混合评分的支持证据因此**比 §5 的计数更弱**：§5 的并集增益（+1 条）建立在含疑点的标签上，
owner 裁定后可能变化。**不得把本分类学当作混合评分的独立确认。**

## 6. 限制（只写真实的）

- 闸门 A 未通过，标签来自单一标注者的 round1；本文件全部 **exploratory + PROVISIONAL**。
- 硬样本只有 **7 个独立场景**；`missing_evidence_check` 的 5 条只覆盖 **3 个场景**，
  其中 onsite 与 vip 两族各含译本孪生/同场景重复，**同型失败的独立证据数小于条数**。
- **5/10 条的人工理由过短或存在疑点**，无法定位到具体缺陷；我没有为它们编造类别或补写理由。
- 分类是**助手判断**（`judgment: agent`），未经第二人复核，不构成人工标注。
- 子集定义本身以「两个评分器都过阈」为入选条件，因此**天然排除了评分器已抓到的失败**，
  不能用来估计评分器的整体漏判率（那由 §5 的 16 条 human fail 全池承担）。
- 新增 API 调用 **0**，新增花费 **$0.00**；全部原话由 `.cache/llm` 离线恢复并通过双重身份校验。

## 7. 核验路径

```bash
# 重新生成硬样本子集与可核对的原始证据（本地、不入库）
.venvs/judge/bin/python scripts/phase4_analysis.py --resamples 2000 --seed 0
# 本文件的结构不变量（类别属冻结词表、每条含 judgment: agent、不泄漏 trace_id）
.venvs/judge/bin/python -m pytest tests/test_phase4_analysis.py
```

逐条核对：`reports/phase4_hard_samples.json`（**已 gitignore**）中
`records[].evidence[N].excerpt` 对应本文 `[N]`，`records[].graders.*.raw` 对应本文原话摘录。
人工理由原文只在 `annotation/labels.csv`（**已 gitignore**），本文一律转述。