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