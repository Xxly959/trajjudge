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