# V2 Phase 0：独立复核与场景映射

只读阶段。**零 API 调用，新增花费 $0.00**。未修改上游 claw-eval / OpenJudge 任何文件。
未生成、猜测或填写任何人工标签。

## 1. 测试状态

| 项 | 结果 |
| --- | --- |
| 原有离线测试 | 214 passed（复核开始时实测） |
| 本阶段新增 | 16 passed（`tests/test_scenario_map.py` 10 个、`tests/test_verify_v2_facts.py` 6 个） |
| 当前全量 | **230 passed in 11.55s**（`make test`） |

新增测试覆盖的是真实出错点，不是形式覆盖：混合类型 keywords 排序崩溃、相对路径导致上游文件找不到、
译文的 schema description 污染结构指纹、同名不同结构被静默并入同一 bootstrap 簇、fixture 形状分歧被静默合并。

## 2. 复核表（报告值 vs 复算值 vs 是否一致）

复算脚本 `scripts/verify_v2_facts.py`，全部从原始 JSONL / CSV / 上游源码独立重算，不读取既有报告的派生值。
机器可读结果：`reports/v2_fact_check.json`；表格：`reports/v2_fact_check.md`。

**11 项检查全部与数据一致（agree=11, disagree=0）。** 但其中 2 项的**报告措辞**与数据含义不符，见第 3 节。

| # | 声明 | 报告值（出处） | 复算值 | 一致 |
| --- | --- | --- | --- | --- |
| 1 | 48 标签 / 2 空白 / 单轮 / 约 30 条无信息量理由 | 48 first-round labels，排除 2 空白（FINAL_REPORT.md:24）；理由质量未被量化 | 50 行，rounds={1:50}，pass 32 / fail 16，空白 `Be5538d`,`Bf3d4a1`；理由长度≤4 字符 **32** 条，命中无信息短语表 **30** 条 | YES（理由质量为新增量化） |
| 2a | Accuracy 与 always-pass 同分；κ / AUC / 漏判 | 32/48=66.7%，κ=0.04，AUC=0.5459，漏判 15/16（FINAL_REPORT.md:29-32；p2.json） | n=48，agreement 0.6667，κ 0.04，AUC 0.5459，漏判 15/16，混淆 tp31/fp15/fn1/tn1 | YES |
| 2b | Comprehensive 同上 | 32/48=66.7%，κ=0.00，AUC=0.6748，漏判 16/16 | n=48，agreement 0.6667，κ 0.0，AUC 0.6748，漏判 16/16，混淆 tp32/fp16/fn0/tn0 | YES |
| 3 | Accuracy 92.1% 顶格；Comprehensive 100% ≥0.6，最低 0.635 | **现有报告与文档均未披露**（grep 无命中） | 1085 条 accuracy 判定，顶格占比 **0.9207**；50 条轨迹曾评分，仅 **6** 条曾非顶格；1035 条 comprehensive，最小 **0.6354**，≥0.6 占比 **1.0** | YES（数值成立，但属未披露事实） |
| 4 | P4 全部 fail→pass 来自 1 条轨迹，n_traj=1 而非 3 | 「24 与 8 个合格配对分别来自 **three and one distinct baseline failures**」（FINAL_REPORT.md:85-86） | distinct_flip_traces=`["1503ef20"]`，distinct_baseline_fail_traces=`["1503ef20"]`；baseline-fail 配对观测 **32**（=off 24 + on 8，跨两个 grader） | 数值 YES / **措辞 NO**，见 3.1 |
| 5 | 32 个 flip_ci 中 16 个零宽 | 未披露；FINAL_REPORT.md:170 仅泛称「可能产生未定义或退化区间」 | analysis 条目 **32**，零宽 flip_ci **16** | YES（属未披露缺陷） |
| 6 | bootstrap 按 task_id 聚簇；51 task_id ≈ 36 场景 | 「51 tasks, 36 paired tasks」（FINAL_REPORT.md:15）；「50 items frozen across **36 tasks**」（:21） | `analysis.py:21` 确用 task_id；语料 51 task_id → **36** 场景；已标注 48 项 = 35 task_id → **28** 场景；人工 fail 16 项 = 13 task_id → **11** 场景；p2 报告簇数 35，p4 簇数 13 | 数值 YES / **「36 tasks」口径 NO**，见 3.2 |
| 7 | voting 复用 average 抽样（0 新调用）；上游 tie_breaker 默认 MIN | 「在共享抽样上比较 Direct/Average/Voting」（FINAL_REPORT.md:139）；未披露复用与 MIN 退化 | `openjudge_bridge.py:60` repeat key 表达式存在；usage：`average api=2/cached=1:48`、`direct api=0/cached=1:48`、`voting api=0/cached=3:48`；**48/48** panel token 完全相同；comprehensive voting<average **12/22**；上游默认 MIN = true | YES（复用与退化属未披露） |
| 8 | 27 条 invalid，其中 19 条在 wrapper=on | 「保留全部 invalid 行，coverage partial」（FINAL_REPORT.md:74-76）；未做缺失非随机性分析 | invalid **27**，on **19** / off **8**；无效率 on **2.2%** vs off **0.93%** | YES（非随机性属新增发现） |
| 9 | wrapper 在 8/8 变体上降低正向膨胀；4/8 comprehensive CI 不重叠；未扰动基线未被压低 | 未以「16/16 对比」形式披露；FINAL_REPORT.md:87-88 只说两个 flip 分母不同、不能证明 wrapper 有益 | grader×variant 对比 **16/16** 全部降低；comprehensive 不重叠 CI 对 **4**；未扰动基线位移 accuracy **+0.1042**（n48，升5/降0）、comprehensive **+0.0250**（n46，升31/降12） | YES（方向为**被低估的正面结果**） |
| 10 | annotate.py 在 round1 有空白时阻塞 round2；无 exclude 子命令 | PROGRESS.md:15「两条一轮标签空白、延迟重标无标签」 | `annotate.py:89` 空白守卫存在；子命令 `[build, check, label, relabel]`；`has_exclude=false`；当前空白 **2** | YES |

## 3. 复算发现的差异（以数据为准）

### 3.1 「three and one distinct baseline failures」是误导性措辞

`FINAL_REPORT.md:85-86` 的 24 与 8 这两个数字本身正确，但它们是**同一条轨迹的重复评估**，不是三条轨迹：

- 轨迹 `1503ef20-6ad8-4780-bd28-ab372d92add4` = `T025zh_ambiguous_contact_email`
  （agent flash think-on，framework passed=True / score 0.9496，人工 fail，盲 ID `B407e62`，
  理由「没有显示张薇的邮信息，根本就没有把张薇当成候选人」）。
- wrapper off：该轨迹 3 次重复全部 baseline-fail → 3 × 8 变体 = **24** 个合格配对。
- wrapper on：只有 1 次重复 baseline-fail → 1 × 8 = **8** 个合格配对。
- 其余 15 条人工 fail 轨迹在两个 grader 上**没有任何** baseline-fail 配对。

因此 P4 的 fail→pass 信号（18/24 与 7/8）**独立轨迹数 = 1，独立场景数 = 1**。
`distinct` 一词用在重复评估上会让读者误以为有 3 条独立失败样本。这是 Phase 1 必须改口径的首要项。

同一条轨迹也是 P3 唯一的 voting 翻转（1.0, 2.0, 1.0）与唯一的 Pro Direct 翻转；
另外 3 条 cohort 轨迹（`0ab402f4`,`0db709b2`,`1191f6b7`）恒为 3.0。

### 3.2 「50 items across 36 tasks」混淆了 task_id 与独立场景

50 个盲标注项确实覆盖 **36 个 task_id**，但只覆盖 **28 个独立场景**；其中 **18 个场景出现多次**。
已标注的 48 项 = 35 task_id = **28 场景**。人工 fail 的 16 项 = 13 task_id = **11 场景**。

现有 bootstrap 以 task_id 为簇（p2=35 簇、p4=13 簇），把 zh/en 译文副本当成独立簇，
**低估了区间宽度**。Phase 1 改为 scenario_id 聚簇后，p2 簇数 35→28、p4 簇数 13→11。

### 3.3 本阶段工具自身的缺陷（已修复并加回归测试）

`build_scenario_map.py` 初版的「结构指纹」把 `tools[].input_schema` 内嵌的 `description`
和 `safety_checks[].description` 计入哈希，而这些字段是**译文**。结果 15 对译文副本的
loose 指纹**全部不同**，初版 36 场景实际是靠 task_id 名称后缀归并出来的，结构证据并未生效。

修复：递归剔除自然语言字段（`_strip_text`）后再哈希。修复后**结构指纹独立地给出同样的 36 组**
（15 对译文 + 21 个单例），名称后缀不再是归并依据。同时修掉两个真实缺陷：

- 同名不同结构会被静默并入同一 scenario_id（进而并入同一 bootstrap 簇）→ 现按指纹消歧并标记。
- fixture 形状分歧原会被静默拆分/合并 → 现保留合并（对簇 bootstrap 是保守方向）但**显式标记并写入 CSV**。

### 3.4 未被任何现有文档披露的事实

第 3、5、7、8 项的数值都成立，但**饱和程度、零宽 CI、voting 抽样复用与 MIN 退化、缺失非随机性**
在 FINAL_REPORT / README / PROGRESS 中均无记载。这些不是算错，而是**漏报**，Phase 1 起必须进入报告正文。

## 4. 场景映射结果

`reports/scenario_map.csv`（51 行，列：task_id, scenario_id, basis, language, category, difficulty,
structure_fingerprint, fixture_content_hash, fixture_shape_hash, fixture_match, scenario_size）。

| 口径 | task_id 数 | 独立场景数 |
| --- | ---: | ---: |
| 全部语料（P2 87 条轨迹涉及） | 51 | **36** |
| 50 个盲标注项 | 36 | **28** |
| 48 个已标注项 | 35 | **28** |
| 16 个人工 fail 项 | 13 | **11** |

归并依据：工具名集合、tool input_schema（剔除译文）、services/端口/命令（路径归一）、
tool_endpoints、scoring_components 名称与权重与 check 签名（keywords 单列）、safety_checks 类型与工具、
primary_dimensions、timeout/max_turns、sandbox_files 数量。自然语言文本与 fixture 文本内容不参与归并。

人工 fail 的 11 个场景：`ambiguous_contact_email`, `api_config_audit`, `competitive_intelligence`,
`complaint_investigation`, `kb_search`, `market_research_report`, `month_end_reconciliation`,
`onsite_support_dispatch`, `order_profit_analysis`, `pinbench_apm_market_research`, `vip_ticket_escalation`。

**对 Phase 3 的影响：≥10 个独立场景的目标已满足（11 个），闸门 B 大概率不需要额外标注。**
即使下面 vip 对子被判定为拆分，场景数变为 12，仍满足目标。

## 5. 需要 owner 确认的对子

`reports/scenario_map_uncertain.json` 共 **7** 条。

### 5.1 必须确认（1 条）：vip_ticket_escalation 的 fixture 形状分歧

`T159zh_vip_ticket_escalation` 与 `T160_vip_ticket_escalation`：结构指纹相同、名称后缀相同、
5 个 fixture 文件中 4 个形状完全一致，仅 `kb/articles.json` 的 **KB-1401** 标签数不同：

| | tags | views |
| --- | --- | ---: |
| zh | `数据库, 连接池, 故障, 排查, DBA`（5 个） | 1567 |
| en | `database, connection pool, troubleshooting, DBA`（4 个） | 1567 |

zh 把 en 的 `troubleshooting` 拆成「故障」「排查」两个标签。KB-1402/1403/1404 的 article_id、views、
标签个数完全一致。

- **选项 A（推荐）：合并为一个场景。** 证据指向翻译产物而非不同任务；合并减少独立单元数，
  对簇 bootstrap 是保守方向（区间更宽）。当前 CSV 已按此处理，`fixture_match=different` 留痕。
- 选项 B：拆成两个场景。人工 fail 场景数 11→12，语料场景数 36→37。若你认为标签数变化会改变
  检索难度、因而不是同一场景，选此项。

### 5.2 建议直接合并（6 条，低风险）

以下 6 对译文副本的 `keywords_present` 列表被翻译，结构其余部分完全一致：
`ambiguous_contact_email`(T025zh/T026)、`cross_service_meeting`(T029zh/T030)、
`escalation_budget_triage`(T031zh/T032)、`ops_review_dashboard`(T033zh/T034)、
`vendor_procurement`(T035zh/T036)、`incident_postmortem`(T037zh/T038)。

推荐合并：关键词列表是评分用的译文字面量，不构成不同场景。其余 9 对译文副本的 keywords 完全相同，
无需确认。**注意**：keywords 被翻译意味着 framework rubric 在 zh/en 上的判定难度可能不同，
这一点会在 Phase 4 的 framework 对比中作为限制说明，而不是当作同一评分条件。

## 6. 工作树说明

仓库中存在**与 v2 无关的未提交改动**（`Makefile`、`README.md`、`docs/THIRD_PARTY.md`、
`src/trajjudge/judging.py` 的 `score_scales` 抽取，以及 dataset / training-candidates / SWE-import /
original-tasks 等未跟踪文件）。这些是先前遗留的在制品，**本阶段未修改、未提交、未清理**。
Phase 0 的 commit 只包含本阶段新增的 4 个脚本/测试文件与 4 个报告产物。
按任务约束，训练候选 / SWE 合并 / 原创可执行任务不再投入，仅 Phase 6 做安全清理。

## 7. 下一步

Phase 0 已完成，无闸门。接下来先写 `docs/PREREG_v2.md` 与 `docs/BUDGET_v2.md` 并 commit，
**在看到任何新实验结果之前**固定阈值方案、主指标、多重比较方法与场景口径；然后进入 Phase 1（零 API 成本）。

等待 owner 对 5.1 的确认；该确认不阻塞 Phase 1（两种选择都会重算，差异会如实报告）。