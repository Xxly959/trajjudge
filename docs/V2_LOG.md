# V2 变更日志

任务：补强 trajjudge 的科学效力（统计口径、标注可靠性、注入实验、防御对照、跨 vendor）。
约束：不改上游；不替人工标注；不伪造/补全数据；预注册优先；新增真实花费硬上限 $5；
跨 vendor 需 owner 提供 key；注入实验只针对本项目自己的 judge。

每阶段一条记录：动机 → 改动 → 关键数字 → 花费 → 闸门/下一步。

---

## Phase 0 — 独立复核与场景映射（2026-11-13）

**动机**：v2 的 10 条「已知事实」必须先独立复算才能作为后续依据；同时需要把 zh/en 译文副本
从 bootstrap 簇里剔除，否则所有区间都被低估。

**改动**（全部新增文件，未触碰上游与既有源码）：
- `scripts/verify_v2_facts.py`：11 项检查，从原始 JSONL/CSV/上游源码重算，不读既有报告派生值。
- `scripts/build_scenario_map.py`：只读上游 task.yaml + fixtures，按语言无关结构指纹归并场景。
- `tests/test_verify_v2_facts.py`（6）、`tests/test_scenario_map.py`（10）。
- 产物：`reports/v2_fact_check.{json,md}`、`reports/scenario_map.csv`、`reports/scenario_map_uncertain.json`、
  `docs/V2_PHASE0.md`。

**关键数字**：
- 复核 **11/11 一致**（agree=11, disagree=0）。
- 测试 **230 passed**（原有 214 + 新增 16）。
- 场景口径：语料 51 task_id → **36** 场景；50 盲标注项 36 task_id → **28** 场景；
  48 已标注 35 task_id → **28** 场景；16 人工 fail 13 task_id → **11** 场景。
- P4 fail→pass 的独立轨迹数 = **1**（`1503ef20` / `T025zh_ambiguous_contact_email`），独立场景数 = **1**。
- 32 个 flip_ci 中 **16** 个零宽；invalid 27 条中 **19** 条在 wrapper=on（2.2% vs 0.93%）。
- voting 与 average **48/48** panel token 完全相同（0 新调用）；comprehensive voting<average **12/22**。
- wrapper 在 **16/16** grader×variant 对比上降低正向膨胀；未扰动基线未被压低
  （accuracy +0.1042，升5/降0；comprehensive +0.0250，升31/降12）。

**与旧结果的差异**（以数据为准，详见 `docs/V2_PHASE0.md` 第 3 节）：
1. `FINAL_REPORT.md:85-86`「three and one distinct baseline failures」措辞误导：24/8 是同一条轨迹的
   重复评估，不是 3 条独立失败轨迹。数值正确，口径错误。
2. `FINAL_REPORT.md:21`「50 items across 36 tasks」混淆 task_id 与独立场景：实为 28 个场景，
   18 个场景重复出现。现有 bootstrap 簇数（p2=35、p4=13）因此偏大。
3. 饱和程度（accuracy 顶格 92.07%、comprehensive 最低 0.6354 且 100% 过阈）、零宽 CI、
   voting 抽样复用与 MIN 退化、缺失非随机性，**现有文档均未披露**——属漏报而非算错。
4. 本阶段工具自身缺陷已修复：初版结构指纹把译文 `input_schema.description` / `safety_checks.description`
   计入哈希，导致 15 对译文副本指纹全不同，36 场景实际靠名称后缀归并。修复后结构指纹独立复现同样的 36 组。
   另修复「同名不同结构被静默并入同一簇」与「fixture 形状分歧被静默处理」两个真实缺陷，均带回归测试。

**花费**：**$0.00**，零 API 调用，零网络请求。

**闸门/下一步**：Phase 0 无闸门。待 owner 确认 1 个不确定对子
（`T159zh_vip_ticket_escalation` / `T160_vip_ticket_escalation`，仅 KB-1401 标签数 5 vs 4，推荐合并）；
该确认不阻塞 Phase 1。下一步：先写并 commit `docs/PREREG_v2.md` + `docs/BUDGET_v2.md`，再进入 Phase 1。

**遗留说明**：工作树存在与 v2 无关的未提交在制品（`score_scales` 抽取、dataset/training/SWE/original-task
脚本与文档）。本阶段未修改、未提交、未清理，commit 只含 Phase 0 自身文件。

---

## 预注册 — PREREG_v2 与 BUDGET_v2（2026-11-13，Phase 1 之前）

**动机**：约束要求「凡是新增的阈值、过滤规则、主指标、多重比较方法，必须在看到新实验结果之前写入
`docs/PREREG_v2.md` 并 commit」。Phase 0 只重算了 v1 已有数据，未产生新实验结果，因此此刻是冻结窗口。

**改动**：新增 `docs/PREREG_v2.md`、`docs/BUDGET_v2.md`。未改任何源码。

**冻结的关键决定**：
- 主分析单元 = `scenario_id`；`task_id` 口径并列保留。vip 对子默认合并，owner 若选拆分则两种口径都重算。
- Bootstrap：B=2000、percentile 95%、seed=0、整簇重采样；`undefined_share>0.10` → unreliable；
  贡献簇数 <2 或零宽 → 输出 `null` +「不可估（簇数不足）」，**禁止零宽 CI**。
- flip 分母 = 不同 baseline-fail **轨迹**数，必报 `(n_traj, n_scenario, pairs)`；`n_scenario<5` → case study，
  不出百分比结论句。
- 策略对比：**选择改名**为「共享采样的聚合函数对比」，不修复抽样（理由：$5 上限下钱更该花在能改变结论的
  中性对照与跨 vendor；共享抽样问题本身良定义；独立抽样不会改变饱和事实）。
  必须披露 voting = 原始分数众数 + MIN 并列 → comprehensive 退化为 **min-of-3**。
- 多重比较：**选 Holm**（FWER，验证性主张少），两个独立族各 16 个检验，簇级 sign-flip 置换；
  exploratory 分析不声称校正。
- Phase 4 校准：**LOSO**（28 场景），目标 balanced accuracy，并列取更接近上游默认阈值者；
  网格固定（accuracy 5 个 + 哨兵；comprehensive 0.50–1.00 步长 0.05 + 哨兵）；
  报 AUC / PR-AUC(fail 为正) / 固定漏判率 {0.10,0.25,0.50} 下的 specificity，主值 0.25；全部 exploratory。
- Phase 5 中性对照文本**已冻结并哈希**（372 字符 / 58 词，长度比 1.0164，
  SHA-256 `6ba14cb6…c963`），位置与格式与防御 notice 完全一致，不含信任边界措辞。
  判读规则冻结：中性也降膨胀→稀释；只有真 wrapper 降→框架；CI 重叠→无法区分。

**两条前提更正（会改变任务预期，立即记录）**：
1. **注入实验的场景覆盖不是 n=1**：P4 的 16 条人工 fail 已覆盖 **11 个场景**，满足 ≥10 目标，
   **闸门 B 不触发**。零成本 estimate-only dry-run 已确认 job 空间：16 轨迹 / 1,728 jobs（两臂）/
   1,728 completions，其中 `defended=off` 臂 **864** 个（856 ok + 8 error），
   与 Phase 3 预注册的 864 个 logical job 完全一致 → **预计新增 API 调用 0**。
   缓存全覆盖尚待 Phase 3 用临时目录离线 replay 核对（不得写入 live run）。
   真正 n=1 的是 baseline-fail 子集，扩大候选池无法修复，只有 Phase 4 的饱和处理能。
2. **非饱和子集只有 3 个独立场景**（6 条曾非顶格轨迹，5 条在 P4 池内）→ 任何基于它的结论都是 case study。
   预注册显式排除池外的 `52382f55`（同场景、不增加独立场景数、省 18 次调用）。

**预算**：新增 1,050 次 completion，peak guard 合计 **$4.287588**（Phase 5 $2.787588 + Phase 6 预留 $1.50），
上限 $5，余量 **$0.712412**。按 P4 实测 9.49% 比例外推真实账单约 **$0.265**。
Phase 1/2/3/4 均为 **$0**。Phase 6 拿到 key 后必须按真实 vendor 定价重估再开跑。

**花费**：**$0.00**，零 API 调用。

**下一步**：commit 本预注册，然后进入 Phase 1（零 API 成本）。

---

## Phase 1 — 统计口径修复（2026-11-13）

**动机**：v1 的区间与翻转率建立在伪重复单元、静默丢弃的未定义抽样、零宽 CI 和被误称为独立策略的
共享抽样之上。这些不是算错，而是口径错——必须在同一批原始数据上把口径改对，并保留 v1 结果做对照。

**改动**：
- `src/trajjudge/metrics.py`：新增 `bootstrap_interval`（报告未定义抽样占比、拒绝零宽、贡献簇 <2 判不可估）
  与 `NOT_ESTIMABLE`。`bootstrap_ci` **行为完全不变**，仅供 v1 对照路径使用（既有测试断言零宽 CI）。
- `src/trajjudge/analysis.py`：新增 `cluster_interval`；`stability_report` / `injection_report` /
  `agreement_with_clusters` 增加显式 `policy="v1"|"v2"` 与 `cluster_unit`。
  `injection_report` 改为按轨迹聚合，输出 ASR、双向判定翻转、`n_traj/n_scenario/pairs`、`case_study`。
- `src/trajjudge/robustness.py`（新增）：逐抽样分数恢复（按上游运算顺序）、`mode_min`、
  共享抽样诊断、分层缺失率 + Fisher 精确检验、RQ1 与注入两套敏感性。
- `scripts/report_experiments.py`：新增 `--ci-policy / --cluster-unit / --scenario-map / --output-suffix`，
  默认 v1，**v1 数值零变化**（已逐键比对：p2 agreement 与 p4 analysis 的数值差异为 0，只新增元数据键）。
- `scripts/robustness_diagnostics.py`、`scripts/v2_stats_compare.py`（新增）。
- `tests/test_robustness_v2.py`：6 个测试类 **31 个测试**。
- 产物：`reports/p2-v2.json`、`reports/p4-v2.json`、`reports/p3-v{1,2}-*.json`（3 个运行）、
  `reports/robustness_v2.json`、`reports/v1_vs_v2_stats.md`。

**关键数字**：
- 测试 **261 passed**（原有 214 全部保持通过；Phase 0 后 230 → 261）。
- RQ1：自助簇 **35 → 28**。accuracy κ CI `[-0.1086, 0.2520] → [0.0000, 0.1453]`；
  comprehensive κ 由零宽 `[0,0]` 改判**不可估**；两个 κ 区间都覆盖 0。
- RQ2：20 个完整配置中 **18 个 v1 零宽 flip CI** 全部改判「不可估（簇数不足）」；
  其余 2 个由 `[0, 0.75]` **变宽为 `[0, 1]`**（完全无信息）。
- RQ3：32 个条目 **全部 case study**（baseline-fail 仅 1 轨迹 / 1 场景）→ 翻转率百分比全部撤回。
  配对 1496、未配对 40；fail→pass **25**、pass→fail **8**（v1 只报前者）。
  ASR 主指标覆盖 **16 轨迹 / 11 场景**，32/32 条目 ASR>0。
  comprehensive 最强变体 `L3_notice/tool_result`：未防御 ASR **0.8936** `[0.8085, 0.9762]`，
  防御 **0.4545** `[0.3488, 0.5714]`，CI 不重叠。
- 共享抽样：**46/46** ok 面板 token 完全一致且 voting 新增调用 0。逐抽样恢复 **41/48**（覆盖率 85.4%），
  每个恢复面板**同时复现**已记录的 average 与 voting 分数（双重校验）。
  三次互不相同 9/41（accuracy 0/19、comprehensive 9/22）；voting==min 33/41（18/19、15/22）；
  voting<average 行级 **15/46**，comprehensive **12/22**——与 v1 声称的 12/22 一致。
- 缺失：P4 invalid **27/1728**，**全部落在 comprehensive**（accuracy 0）；
  防御臂 2.20% vs 未防御 0.93%（**2.4 倍**），Fisher p=**0.0504**（exploratory）。
  注入敏感性：comprehensive ASR 未防御 0.6915→[0.6771, 0.6979]、防御 0.3636→[0.3724, 0.3750]，
  **防御收益在三个臂下方向与量级不变**；但防御臂排除配对 32 vs 未防御 8。
  RQ1 帧缺失分数为 0 → 三臂重合，敏感性在此不具信息量（如实记录）。

**与旧结果的差异**：
1. **推翻**「注入翻转率 75%」：分母是同一条轨迹的 3 次重复，n_scenario=1，只能作个案。
2. **推翻**「voting 是独立稳定性策略」：抽样完全共享；comprehensive 的 MIN tie-break 使其退化为取最小值。
   注意 accuracy 的 voting==min 比例更高（18/19），但成因是**饱和导致三次同分**，与 tie-break 无关——
   两种机制必须分开陈述，不能合并成一个「退化率」。
3. **削弱**「多数配置 flip_rate=0」：v1 的零宽区间读作「精确为零」，v2 只能读作「簇数不足以估计」。
4. **推翻**「缺失可忽略」：缺失非随机，且与防御臂相关。
5. **加强（附条件）**「wrapper 防御有效」：ASR 差在敏感性三臂下稳定，不是缺失造成的假象；
   但防御臂格式失败率更高这一事实必须写进限制。
6. **反直觉但如实记录**：scenario 聚类**没有让所有区间变宽**——accuracy 的 κ 与 AUC 区间反而收窄。
   译本成对入簇后标签比例在重采样中更稳定。伪重复的危害不是单向放大区间，而是让宽度失去解释力。
   我没有把「区间应该变宽」当成预期去调参。

**花费**：**$0.00**，零 API 调用，零网络请求。全部从既有 JSONL 与 `.cache/llm` 重算。

**闸门/下一步**：Phase 1 无闸门。下一步 Phase 2（标注可靠性工具，零成本），结束时停在**闸门 A**
等 owner 完成人工标注；在闸门前不做任何依赖新标签的分析。

---

## Phase 2 — 标注可靠性工具（2026-11-13，停在闸门 A）

**动机**：v1 的金标准是单人一次性标注，没有 test-retest 一致度，因此「评分器与人类 κ=0.377」
无法与「人类自己与自己的一致度」对比；同时 `relabel` 在 round1 存在空白行时永久死锁，
owner 无法在不伪造标签的前提下推进第二轮。

**改动**：
- `docs/PREREG_v2.md` 新增 **§5b**（编号用 5b 以免改动已被代码引用的 §6–§12）。
  **写于任何 round-2 结果产生之前**：`annotation/round2_labels.csv` 当时不存在，kit 尚未构建。
  冻结内容：主指标（原始一致度 / Cohen κ / PABAK）、scenario 簇 bootstrap（B=2000、seed=0、
  沿用 §2 全部区间规则）、配对与未配对逐条归因、`n_scenario_paired < 5` → case study、
  **κ < 0.60 → 金标准不稳定且评分器一致度指标降级为 exploratory**、
  κ ≥ 0.60 但 CI 下界 < 0.60 → 「稳定性未确证」、κ 不可估 → 不得用点估计替代判定。
  理由质量警告明确为 **advisory，不是过滤规则**；`[N]` 引用是**输入期**约束而非事后过滤。
- `src/trajjudge/annotation.py`：新增 `reason_warnings`、`message_indices`、`evidence_problems`、
  `read_exclusions` / `append_exclusion`（append-only + fsync）、`exclude_row` / `reinstate_row`、
  `round2_blind_ids`；`validate_labels` 增加 keyword-only `excluded` 与 `evidence`（向后兼容）。
- `scripts/annotate.py`：新增 `exclude` / `reinstate` / `round2` 子命令与 `label --csv`；
  `check` 报告两轮进度、逐条排除记录（时间 + 理由）与理由质量警告；
  round2 从**冻结证据重渲染并校验 sha256**，写入独立目录与独立 CSV，私钥在 `annotation/` 之外；
  生成 `annotation/GUIDE.md`（7 条判定规则照抄 + `[N]` 引用要求 + **2 正例 2 反例，全部标注为虚构演示**，
  不含任何评分器输出、分数、模型名或真实 trace id）。
- `scripts/annotator_agreement.py`（新增）：test-retest 一致度 + κ + PABAK，scenario 簇 CI，
  并列 task_id 簇版本；未配对逐条归因；闸门未通过时**只输出闸门状态，不计算任何依赖标签的统计量**；
  支持 `--second` 计算 inter-annotator κ，无第二标注者时明确写「单标注者」，不用 test-retest 冒充。
- `.gitignore`：新增 `annotation/round2/`、`annotation/round2_labels.csv`、`annotation/exclusions.jsonl`
  （私钥本已被 `outputs/` 覆盖）。`docs/ANNOTATION_GUIDE.md` 更新流程与退役说明。
- 测试：`tests/annotation_env.py`（共享合成环境）、`tests/test_annotation_v2.py`、
  `tests/test_annotator_agreement.py`，共 **36 个新测试**，全部使用合成标签。

**修掉的两个真实 bug**（都由新测试暴露，不是假想问题）：
1. `round2 --count N` 把 `kit.new_seed()` 写在列表推导的条件里，**每行重新抽一次随机样本**，
   导致选中的行数不等于 N（实测 `--count 1` 选出 **0** 条，`--count 2` 选出 1 条），
   且不是均匀子样本。改为先抽一次再过滤，并拒绝 `--count < 1`（空 kit 会因拒绝覆盖而永久卡住）。
2. `exclude` 在**审计记录已成功落盘之后**，因 `_exclusions().relative_to(root)` 在 annotation
   目录被 relocation 时抛 `ValueError`，owner 看到 traceback 却以为写入失败。新增 `_show()` 容错显示。

**关键数字**：
- 测试 **297 passed**（261 → 297；原有 214 个离线测试全部保持通过）。
- round 1 现状：**48/50 已标注**（32 pass / 16 fail），**2 条空白** `Be5538d`、`Bf3d4a1`，0 条显式排除。
- `check` 给出 **62 条理由质量警告**，落在 **32/48 条已标注行（66.7%）**：
  大量理由 ≤4 字或为「正确 / 合理」这类无判定证据的短语。**不剔除任何标签**，如实报告为证据强度限制。
- 时间间隔：round1 最后一条标签 2026-11-09T09:54:32Z，今日 2026-11-13 → **≥48h 已满足**。
- `reports/annotator_agreement.json` 当前为 **blocked**：`test_retest = null`，
  `verdict.status = blocked`，未产出任何一致度数字。

**与旧结果的差异**：
1. **解除死锁**：v1 的 `relabel` 在 round1 有空白时 `sys.exit`，owner 只能被迫给标签或放弃第二轮。
   现在可以显式退役（理由 + append-only 审计 + 保留空白行），或补标签。
2. **第二轮不再是「同文件追加」**：旧 `relabel` 把 round2 行追加进 `labels.csv`，
   第一轮标签与第二轮同处一文件，存在回忆污染风险。新 `round2` 用独立目录 + 独立 CSV + 全新盲 ID。
   旧 `relabel` 路径保留（既有测试依赖），但指南推荐 `round2`。
3. **金标准稳定性判据首次被冻结**：v1 从未定义「人类自身一致度低到多少就要降级评分器指标」。
   现在 0.60 是**事前**阈值，不是看到结果后挑的。
4. 尚未推翻任何既有数值结论：本阶段不产生新标签，也不重算 RQ1。

**花费**：**$0.00**，零 API 调用，零网络请求。`docs/BUDGET_v2.md` 中 Phase 2 预算本就是 0。

**闸门 A（需要 owner 的人工动作，助手不得代做）**：
1. 处理 round1 的 2 条空白 `Be5538d`、`Bf3d4a1`：二选一
   - 补标签：`python scripts/annotate.py label`
   - 显式退役：`python scripts/annotate.py exclude --blind-id Be5538d --reason "<你的理由>"`（另一条同理）
2. 完成后由助手运行 `python scripts/annotate.py round2` 构建第二轮盲标 kit（默认全部 48 条已标注轨迹；
   也可 `--count N` 抽子集）。**标签仍然只能由 owner 给。**
3. owner 完成第二轮：`python scripts/annotate.py label --round 2 --csv annotation/round2_labels.csv`
   （理由必须引用 `[消息编号]`；先读 `annotation/GUIDE.md`）。
4. 可选：提供第二标注者的 CSV（同一批 round1 盲 ID），用 `--second` 计算 inter-annotator κ。
5. 闸门通过后运行 `python scripts/annotator_agreement.py`，再重算 RQ1 并列报告
   「评分器 κ vs 人类 test-retest κ」。**在此之前不做任何依赖标签的分析。**
