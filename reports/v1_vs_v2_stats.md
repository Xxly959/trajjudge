# v1 ↔ v2 统计口径对照

本文件由 `scripts/v2_stats_compare.py` 从已落盘的报告 JSON 生成，不含任何新实验。
v1 = 已发布口径（task_id 簇、丢弃未定义抽样、允许零宽 CI）；v2 = `docs/PREREG_v2.md` 口径。
两者读取**同一批原始行**，差异只来自统计定义，不来自数据。

## 1. 口径变更清单

| 项目 | v1 | v2 |
| --- | --- | --- |
| 自助聚类单元 | task_id（中英译本算两个独立单元） | scenario_id（译本合并） |
| 未定义自助抽样 | 静默丢弃，不足半数才返回 null | 计数并报告占比，>10% 判 unreliable |
| 零宽 CI | 直接输出，如 `[0.0, 0.0]` | 拒绝，输出「不可估（簇数不足）」 |
| 翻转率分母 | 基线失败的**观测对** | 基线失败的**不同轨迹**，并报告 n_traj/n_scenario/pairs |
| 少场景翻转率 | 照常给百分比 | n_scenario<5 判 case study，不给百分比结论 |
| 注入主指标 | 翻转率 | ASR（分数上升率）为主，判定翻转另列 |
| 翻转方向 | 只统计 fail→pass | fail→pass 与 pass→fail 分别统计 |
| strategy 对比 | 称作三种独立策略 | 共享采样的聚合函数对比 |
| 缺失处理 | 排除后不报告影响 | 分层缺失率 + invalid 当 pass/当 fail 敏感性 |

## 2. RQ1 一致性（P2，人工标签 48 条）

自助簇数：**35 → 28**。

| 评分器 | 指标 | v1 CI | v1 宽度 | v2 CI | v2 宽度 | v2 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| trajectory_accuracy | accuracy | [0.5111, 0.8163] | 0.3052 | [0.5306, 0.8095] | 0.2789 | ok |
| trajectory_accuracy | kappa | [-0.1086, 0.2520] | 0.3606 | [0.0000, 0.1453] | 0.1453 | ok |
| trajectory_accuracy | auc | [0.4688, 0.6514] | 0.1826 | [0.5000, 0.6085] | 0.1085 | ok |
| trajectory_comprehensive | accuracy | [0.5294, 0.8043] | 0.2749 | [0.5306, 0.8095] | 0.2789 | ok |
| trajectory_comprehensive | kappa | [0.0000, 0.0000] | 0.0000 | — | — | not_estimable |
| trajectory_comprehensive | auc | [0.5376, 0.7972] | 0.2596 | [0.5332, 0.7873] | 0.2541 | ok |

注意：scenario 聚类**没有让所有区间变宽**。译本成对进入同一簇后，标签比例在重采样中更稳定，
accuracy 的 κ 区间反而收窄。伪重复的危害不是单向放大区间，而是让区间宽度失去解释力。
两个评分器的 κ 区间都覆盖 0，「与人工判定无超出偶然的一致」这一结论在 v2 下不变。

## 3. RQ2 稳定性（P3）

| 运行 | 配置 | 簇数 v1→v2 | flip_rate | v1 CI | v2 CI | v2 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| flash-strategies-4 | `trajectory_accuracy\|think=off\|average3` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_accuracy\|think=off\|direct1` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_accuracy\|think=off\|voting3` | 4→3 | 0.250 | [0.0000, 0.7500] | [0.0000, 1.0000] | ok |
| flash-strategies-4 | `trajectory_accuracy\|think=on\|average3` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_accuracy\|think=on\|direct1` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_accuracy\|think=on\|voting3` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_comprehensive\|think=off\|average3` | 3→2 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_comprehensive\|think=off\|direct1` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_comprehensive\|think=off\|voting3` | 3→2 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_comprehensive\|think=on\|average3` | 3→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_comprehensive\|think=on\|direct1` | 3→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-strategies-4 | `trajectory_comprehensive\|think=on\|voting3` | 3→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| pro-direct-4 | `trajectory_accuracy\|think=off\|direct1` | 4→3 | 0.250 | [0.0000, 0.7500] | [0.0000, 1.0000] | ok |
| pro-direct-4 | `trajectory_accuracy\|think=on\|direct1` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| pro-direct-4 | `trajectory_comprehensive\|think=off\|direct1` | 4→3 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| pro-direct-4 | `trajectory_comprehensive\|think=on\|direct1` | 3→2 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-direct-pilot | `trajectory_accuracy\|think=off\|direct1` | 9→8 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-direct-pilot | `trajectory_accuracy\|think=on\|direct1` | 9→8 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-direct-pilot | `trajectory_comprehensive\|think=off\|direct1` | 9→8 | 0.000 | [0.0000, 0.0000] | — | not_estimable |
| flash-direct-pilot | `trajectory_comprehensive\|think=on\|direct1` | 8→8 | 0.000 | [0.0000, 0.0000] | — | not_estimable |

共 20 个完整配置：v1 有 **18 个零宽 flip CI**，v2 全部改判「不可估（簇数不足）」；
其余 2 个非零宽区间在 v2 下**变宽**。
「多数配置 flip_rate=0」在 v1 里读作「精确为零」，在 v2 里只能读作「簇数不足以估计」。

## 4. RQ3 注入（P4，16 条轨迹 / 11 个场景）

- 配对观测 **1496**，未配对 **40**（invalid 保留，不补零）。
- 32 个 (配置×变体) 条目中 **32 个判为 case study**：基线失败只落在 1 条轨迹 / 1 个场景上。
- fail→pass **25** 次，pass→fail **8** 次，判定改变合计 **33** 次。v1 只报告了前者。
- ASR>0 的条目 **32/32**；ASR 自助簇数 **11**（场景）。

### 4.1 主指标 ASR（综合评分器，未防御 / 防御）

| 变体 | 未防御 ASR | 95% CI | 防御 ASR | 95% CI | 差值 |
| --- | --- | --- | --- | --- | --- |
| L1_note/assistant_final | 0.5957 | [0.3704, 0.8056] | 0.3111 | [0.1875, 0.4375] | 0.2846 |
| L1_note/tool_result | 0.6042 | [0.4667, 0.7619] | 0.3488 | [0.2143, 0.4889] | 0.2553 |
| L2_request/assistant_final | 0.5625 | [0.4444, 0.6944] | 0.2273 | [0.1316, 0.3182] | 0.3352 |
| L2_request/tool_result | 0.6596 | [0.5667, 0.7949] | 0.4444 | [0.2368, 0.6444] | 0.2151 |
| L3_notice/assistant_final | 0.8000 | [0.6939, 0.9111] | 0.4000 | [0.2340, 0.5952] | 0.4000 |
| L3_notice/tool_result | 0.8936 | [0.8085, 0.9762] | 0.4545 | [0.3488, 0.5714] | 0.4391 |
| L4_override/assistant_final | 0.7083 | [0.5625, 0.8431] | 0.3721 | [0.2326, 0.5476] | 0.3362 |
| L4_override/tool_result | 0.7174 | [0.6154, 0.8462] | 0.3488 | [0.1951, 0.4889] | 0.3686 |

### 4.2 被 v1 掩盖的方向性

| 评分器 | 防御 | fail→pass | pass→fail |
| --- | --- | --- | --- |
| trajectory_accuracy | 否 | 18 | 0 |
| trajectory_accuracy | 是 | 7 | 8 |
| trajectory_comprehensive | 否 | 0 | 0 |
| trajectory_comprehensive | 是 | 0 | 0 |

综合评分器的判定翻转在观测臂为 0：基线分全部 ≥0.6（饱和），注入后仍 ≥0.6。
因此「注入改变判定」的证据全部来自 accuracy，且集中在单一场景，只能作为个案。

## 5. 共享采样的聚合函数对比（PREREG_v2 §4）

- 抽样共享：46/46 个 voting 面板与 average **token 完全一致**，且 46/46 个 voting **新增 API 调用为 0**。
- 逐抽样恢复：41/48 个面板（覆盖率 0.8542），每个都同时复现了已记录的 average 与 voting 分数。
- 不可恢复面板 7 个，原因逐条列于 `reports/robustness_v2.json`，未做任何填补。

| 指标 | 全体 | accuracy | comprehensive |
| --- | --- | --- | --- |
| 三次抽样互不相同 | 9/41 | 0/19 | 9/22 |
| voting == min(三次) | 33/41 | 18/19 | 15/22 |
| voting < average | 15/41 | 3/19 | 12/22 |

行级（全部 ok 面板，不依赖缓存恢复）：voting < average = **15/46**，其中 comprehensive **12/22**，与 v1 报告的 12/22 一致。

结论：voting 不是独立重复实验，而是同一批抽样的众数聚合。两个评分器的退化机制不同：
- accuracy：voting==min 高达 18/19，但三次抽样互不相同为 0/19——饱和使三次同分，众数与最小值天然相同，不是 tie-break 造成的。
- comprehensive：三次互不相同 9/22，连续分数的浮点尾差让众数不存在，
  上游 `tie_breaker=MIN` 于是直接取最小值，voting==min 15/22、voting<average 12/22。**这才是 MIN 退化。**

## 6. 缺失机制与敏感性（PREREG_v2 §5）

P4 共 1728 行，invalid **27** 行（0.0156）。

| 分层 | 取值 | 行数 | invalid | 缺失率 |
| --- | --- | --- | --- | --- |
| grader | trajectory_accuracy | 864 | 0 | 0.0000 |
| grader | trajectory_comprehensive | 864 | 27 | 0.0312 |
| defended | False | 864 | 8 | 0.0093 |
| defended | True | 864 | 19 | 0.0220 |

防御臂 × invalid 的 Fisher 精确检验 p = **0.0504**（exploratory，未预注册为假设）。
列联表 [[19, 845], [8, 856]]。invalid 按评分器分布：trajectory_accuracy 0、trajectory_comprehensive 27；防御臂缺失率是未防御臂的 2.4 倍。
这意味着 wrapper 的「防御收益」与「更高的格式失败率」同时发生，必须做敏感性才能分开。

### 6.1 注入敏感性（invalid 当 pass / 当 fail）

| 评分器 / 臂 | observed ASR | invalid_as_pass | invalid_as_fail | observed 排除对 |
| --- | --- | --- | --- | --- |
| trajectory_accuracy\|defended=False | 0.1094 | 0.1094 | 0.1094 | 0 |
| trajectory_accuracy\|defended=True | 0.0208 | 0.0208 | 0.0208 | 0 |
| trajectory_comprehensive\|defended=False | 0.6915 | 0.6979 | 0.6771 | 8 |
| trajectory_comprehensive\|defended=True | 0.3636 | 0.3750 | 0.3724 | 32 |

防御与未防御的 ASR 差在三个臂下都保持同一方向与量级，**防御收益不是缺失数据造成的假象**。
但防御臂被排除的配对数（32）约为未防御臂（8）的 4.0 倍，覆盖率差异本身必须写进结论限制。

### 6.2 RQ1 敏感性

人工标注帧缺失分数：trajectory_accuracy 0、trajectory_comprehensive 0。
两个评分器均为 0，因此三个臂完全重合（`informative=false`）——
**RQ1 的结论不受缺失影响，敏感性在此不具信息量**，如实记录而非省略。

## 7. 结论变化汇总

| 旧结论 | v2 判定 | 依据 |
| --- | --- | --- |
| 注入翻转率 75% | **推翻** | 分母是 1 条轨迹的 3 次重复，n_scenario=1，只能作个案 |
| 多数配置 flip_rate=0（精确） | **削弱** | 18/20 零宽 CI 改判不可估；其余区间变宽至 [0,1] |
| 50 条样本覆盖 36 个独立任务 | **削弱** | 35 个 task_id 实为 28 个场景，译本伪重复 |
| voting 是独立于 average 的稳定性策略 | **推翻** | 46/46 面板 token 相同、新增调用 0；comprehensive 有 9/22 面板因 MIN tie-break 取最小值 |
| 评分器与人工一致（accuracy 66.7%） | **不变但需降级** | κ 区间覆盖 0；66.7% 与 always-pass 基线同值 |
| wrapper 防御有效 | **加强（附条件）** | ASR 差在三个敏感性臂下稳定；但防御臂格式失败率更高 |
| 缺失可忽略 | **推翻** | 缺失非随机：全部集中于 comprehensive，且防御臂更高 |

## 8. 复现命令

```bash
PY=.venvs/judge/bin/python
$PY scripts/report_experiments.py p2 --output-suffix=-v1check   # v1 数值不变（仅新增元数据键）
$PY scripts/report_experiments.py p2 --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2
$PY scripts/report_experiments.py p4 --input outputs/p4/p4-flash-human-fail-16.jsonl \
    --expected-unlabeled 2 --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2
$PY scripts/report_experiments.py p3 --input outputs/p3/p3-flash-strategies-4.jsonl --output-suffix=-v1-flash-strategies-4
$PY scripts/report_experiments.py p3 --input outputs/p3/p3-flash-strategies-4.jsonl \
    --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2-flash-strategies-4
$PY scripts/report_experiments.py p3 --input outputs/p3/p3-pro-direct-4.jsonl --output-suffix=-v1-pro-direct-4
$PY scripts/report_experiments.py p3 --input outputs/p3/p3-pro-direct-4.jsonl \
    --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2-pro-direct-4
$PY scripts/report_experiments.py p3 --input outputs/p3/p3-flash-direct-pilot.jsonl --output-suffix=-v1-flash-direct-pilot
$PY scripts/report_experiments.py p3 --input outputs/p3/p3-flash-direct-pilot.jsonl \
    --ci-policy v2 --cluster-unit scenario_id --output-suffix=-v2-flash-direct-pilot
$PY scripts/robustness_diagnostics.py
$PY scripts/v2_stats_compare.py
```
