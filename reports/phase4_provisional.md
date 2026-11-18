# Phase 4 — 阈值校准与饱和处理（PROVISIONAL / exploratory）

> **PROVISIONAL**：依赖 round1 人工标签，闸门 A 未通过。按 PREREG_v2 §7/§7b 全部标 **exploratory**，
> **不得**写入 `FINAL_REPORT_v2.md` 或 `RESUME_CLAIMS.md`。若人类 test-retest κ < 0.60，永久降级为 exploratory。
> 评分器原话与逐轨迹明细只在 `reports/` 内；round2 完成前不得进入 `GUIDE.md`、kit 或任何标注视图。

## 1. 样本与场景口径

- 已连接标签轨迹 **48**（候选 50），缺失分数：{'trajectory_accuracy': 0, 'trajectory_comprehensive': 0}。
- 独立场景 **28**（merge 主口径）/ **29**（split 敏感性口径）。
- LOSO：每折留出**整个场景**，译本孪生同折；阈值只在训练折上选，指标只由 out-of-fold 预测池化后计算。

## 2. 上游默认阈值下的三者对比（framework rubric vs 两个 LLM grader）

| 评分器 | n | 场景 | accuracy | κ | PABAK | balanced acc | 漏判率 | AUC(pass) | PR-AUC(fail) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| framework rubric（可执行检查） | 48 | 28 | 0.7708 | 0.3774 | 0.5417 | 0.6562 | 0.6875 | — | — |
| trajectory_accuracy | 48 | 28 | 0.6667 | 0.0400 | 0.3333 | 0.5156 | 0.9375 | 0.5459 | 0.3646 |
| trajectory_comprehensive | 48 | 28 | 0.6667 | 0.0000 | 0.3333 | 0.5000 | 1.0000 | 0.6748 | 0.5402 |

- framework 的 AUC / PR-AUC：**不适用（二值 rubric，无连续分数）**，不填 0.5。
- 漏判率 = human fail 中被判 pass 的比例；正类 = pass，故漏判 = false positive。

### 2b. 区间（scenario 簇 bootstrap，B=2000、percentile 95%、seed=0）

| 评分器 | 指标 | 点估计 | 95% CI | 状态 |
| --- | --- | ---: | --- | --- |
| framework | accuracy | 0.7708 | [0.6481, 0.8974] | ok |
| framework | kappa | 0.3774 | [0.0949, 0.6874] | ok |
| framework | balanced_accuracy | 0.6562 | [0.5357, 0.8000] | ok |
| framework | miss_rate | 0.6875 | [0.4000, 0.9286] | ok |
| framework | auc_pass | — | — | — |
| framework | pr_auc_fail | — | — | — |
| trajectory_accuracy | accuracy | 0.6667 | [0.5306, 0.8085] | ok |
| trajectory_accuracy | kappa | 0.0400 | [0.0000, 0.1500] | ok |
| trajectory_accuracy | balanced_accuracy | 0.5156 | [0.5000, 0.5583] | ok |
| trajectory_accuracy | miss_rate | 0.9375 | [0.8000, 1.0000] | ok |
| trajectory_accuracy | auc_pass | 0.5459 | [0.5000, 0.6103] | ok |
| trajectory_accuracy | pr_auc_fail | 0.3646 | [0.2245, 0.5072] | ok |
| trajectory_comprehensive | accuracy | 0.6667 | [0.5306, 0.8085] | ok |
| trajectory_comprehensive | kappa | 0.0000 | not_estimable（不可估（簇数不足）） | not_estimable |
| trajectory_comprehensive | balanced_accuracy | 0.5000 | not_estimable（不可估（簇数不足）） | not_estimable |
| trajectory_comprehensive | miss_rate | 1.0000 | not_estimable（不可估（簇数不足）） | not_estimable |
| trajectory_comprehensive | auc_pass | 0.6748 | [0.5161, 0.7913] | ok |
| trajectory_comprehensive | pr_auc_fail | 0.5402 | [0.3709, 0.6637] | ok |

## 3. LOSO 阈值校准（主指标 = balanced accuracy）

### 3.1 `merge`（主口径）

| grader | 目标 | 折数 | 未定义折 | 选出阈值（计数） | OOF n | κ | balanced acc | 漏判率 | AUC | AUC CI 覆盖 0.5 |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| trajectory_accuracy | balanced | 28 | 0 | threshold:2.0×1, threshold:2.5×27 | 48 | 0.0400 | 0.5156 | 0.9375 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_accuracy | miss_0.10 | 28 | 0 | always_fail×28 | 48 | -0.0000 | 0.5000 | 0.0000 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_accuracy | miss_0.25 | 28 | 0 | always_fail×28 | 48 | -0.0000 | 0.5000 | 0.0000 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_accuracy | miss_0.50 | 28 | 0 | always_fail×28 | 48 | -0.0000 | 0.5000 | 0.0000 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_comprehensive | balanced | 28 | 0 | threshold:0.8×25, threshold:0.95×3 | 48 | 0.2373 | 0.6094 | 0.6250 | 0.6748 | 否 |
| trajectory_comprehensive | miss_0.10 | 28 | 0 | threshold:0.95×28 | 48 | 0.1628 | 0.6094 | 0.0625 | 0.6748 | 否 |
| trajectory_comprehensive | miss_0.25 | 28 | 0 | threshold:0.95×28 | 48 | 0.1628 | 0.6094 | 0.0625 | 0.6748 | 否 |
| trajectory_comprehensive | miss_0.50 | 28 | 0 | threshold:0.85×1, threshold:0.9×27 | 48 | 0.1127 | 0.5625 | 0.4375 | 0.6748 | 否 |

### 3.2 `split`（敏感性口径）

| grader | 目标 | 折数 | 未定义折 | 选出阈值（计数） | OOF n | κ | balanced acc | 漏判率 | AUC | AUC CI 覆盖 0.5 |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| trajectory_accuracy | balanced | 29 | 0 | threshold:2.0×1, threshold:2.5×28 | 48 | 0.0400 | 0.5156 | 0.9375 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_accuracy | miss_0.10 | 29 | 0 | always_fail×29 | 48 | -0.0000 | 0.5000 | 0.0000 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_accuracy | miss_0.25 | 29 | 0 | always_fail×29 | 48 | -0.0000 | 0.5000 | 0.0000 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_accuracy | miss_0.50 | 29 | 0 | always_fail×29 | 48 | -0.0000 | 0.5000 | 0.0000 | 0.5459 | 是 → 无证据支持可用区分度 |
| trajectory_comprehensive | balanced | 29 | 0 | threshold:0.8×26, threshold:0.95×3 | 48 | 0.2373 | 0.6094 | 0.6250 | 0.6748 | 否 |
| trajectory_comprehensive | miss_0.10 | 29 | 0 | threshold:0.95×29 | 48 | 0.1628 | 0.6094 | 0.0625 | 0.6748 | 否 |
| trajectory_comprehensive | miss_0.25 | 29 | 0 | threshold:0.95×29 | 48 | 0.1628 | 0.6094 | 0.0625 | 0.6748 | 否 |
| trajectory_comprehensive | miss_0.50 | 29 | 0 | threshold:0.85×1, threshold:0.9×28 | 48 | 0.1127 | 0.5625 | 0.4375 | 0.6748 | 否 |

**两臂并列**（§7b）：`calibrated_only` 为主指标池；`with_fallback` 含未定义折改用上游默认阈值的预测，只作敏感性臂。未定义折不得静默丢弃。

| 口径 | grader | 目标 | 臂 | OOF n | 未定义折占比 | accuracy | κ | specificity | 漏判率 |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| merge | trajectory_accuracy | balanced | calibrated_only | 48 | 0.0000 | 0.6667 | 0.0400 | 0.0625 | 0.9375 |
| merge | trajectory_accuracy | balanced | with_fallback | 48 | 0.0000 | 0.6667 | 0.0400 | 0.0625 | 0.9375 |
| merge | trajectory_accuracy | miss_0.10 | calibrated_only | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| merge | trajectory_accuracy | miss_0.10 | with_fallback | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| merge | trajectory_accuracy | miss_0.25 | calibrated_only | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| merge | trajectory_accuracy | miss_0.25 | with_fallback | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| merge | trajectory_accuracy | miss_0.50 | calibrated_only | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| merge | trajectory_accuracy | miss_0.50 | with_fallback | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| merge | trajectory_comprehensive | balanced | calibrated_only | 48 | 0.0000 | 0.6875 | 0.2373 | 0.3750 | 0.6250 |
| merge | trajectory_comprehensive | balanced | with_fallback | 48 | 0.0000 | 0.6875 | 0.2373 | 0.3750 | 0.6250 |
| merge | trajectory_comprehensive | miss_0.10 | calibrated_only | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| merge | trajectory_comprehensive | miss_0.10 | with_fallback | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| merge | trajectory_comprehensive | miss_0.25 | calibrated_only | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| merge | trajectory_comprehensive | miss_0.25 | with_fallback | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| merge | trajectory_comprehensive | miss_0.50 | calibrated_only | 48 | 0.0000 | 0.5625 | 0.1127 | 0.5625 | 0.4375 |
| merge | trajectory_comprehensive | miss_0.50 | with_fallback | 48 | 0.0000 | 0.5625 | 0.1127 | 0.5625 | 0.4375 |
| split | trajectory_accuracy | balanced | calibrated_only | 48 | 0.0000 | 0.6667 | 0.0400 | 0.0625 | 0.9375 |
| split | trajectory_accuracy | balanced | with_fallback | 48 | 0.0000 | 0.6667 | 0.0400 | 0.0625 | 0.9375 |
| split | trajectory_accuracy | miss_0.10 | calibrated_only | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| split | trajectory_accuracy | miss_0.10 | with_fallback | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| split | trajectory_accuracy | miss_0.25 | calibrated_only | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| split | trajectory_accuracy | miss_0.25 | with_fallback | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| split | trajectory_accuracy | miss_0.50 | calibrated_only | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| split | trajectory_accuracy | miss_0.50 | with_fallback | 48 | 0.0000 | 0.3333 | -0.0000 | 1.0000 | 0.0000 |
| split | trajectory_comprehensive | balanced | calibrated_only | 48 | 0.0000 | 0.6875 | 0.2373 | 0.3750 | 0.6250 |
| split | trajectory_comprehensive | balanced | with_fallback | 48 | 0.0000 | 0.6875 | 0.2373 | 0.3750 | 0.6250 |
| split | trajectory_comprehensive | miss_0.10 | calibrated_only | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| split | trajectory_comprehensive | miss_0.10 | with_fallback | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| split | trajectory_comprehensive | miss_0.25 | calibrated_only | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| split | trajectory_comprehensive | miss_0.25 | with_fallback | 48 | 0.0000 | 0.5000 | 0.1628 | 0.9375 | 0.0625 |
| split | trajectory_comprehensive | miss_0.50 | calibrated_only | 48 | 0.0000 | 0.5625 | 0.1127 | 0.5625 | 0.4375 |
| split | trajectory_comprehensive | miss_0.50 | with_fallback | 48 | 0.0000 | 0.5625 | 0.1127 | 0.5625 | 0.4375 |

### 3b. 固定漏判率下的 specificity（主值 0.25）

选点规则（§7b 冻结）：训练折上取 `train_miss_rate ≤ target` 中最接近 target 的网格点，并列取更接近上游默认阈值；`always_fail` 漏判率为 0，故任何非负 target 都可满足。

| 口径 | grader | target | 选出阈值 | OOF specificity | specificity CI | OOF sensitivity | 漏判率 | 未定义折 |
| --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| merge | trajectory_accuracy | 0.10 | always_fail×28 | 1.0000 | not_estimable（不可估（簇数不足）） | 0.0000 | 0.0000 | 0 |
| merge | trajectory_accuracy | 0.25（主值） | always_fail×28 | 1.0000 | not_estimable（不可估（簇数不足）） | 0.0000 | 0.0000 | 0 |
| merge | trajectory_accuracy | 0.50 | always_fail×28 | 1.0000 | not_estimable（不可估（簇数不足）） | 0.0000 | 0.0000 | 0 |
| merge | trajectory_comprehensive | 0.10 | threshold:0.95×28 | 0.9375 | [0.7692, 1.0000] | 0.2812 | 0.0625 | 0 |
| merge | trajectory_comprehensive | 0.25（主值） | threshold:0.95×28 | 0.9375 | [0.7692, 1.0000] | 0.2812 | 0.0625 | 0 |
| merge | trajectory_comprehensive | 0.50 | threshold:0.85×1, threshold:0.9×27 | 0.5625 | [0.2273, 0.8333] | 0.5625 | 0.4375 | 0 |
| split | trajectory_accuracy | 0.10 | always_fail×29 | 1.0000 | not_estimable（不可估（簇数不足）） | 0.0000 | 0.0000 | 0 |
| split | trajectory_accuracy | 0.25（主值） | always_fail×29 | 1.0000 | not_estimable（不可估（簇数不足）） | 0.0000 | 0.0000 | 0 |
| split | trajectory_accuracy | 0.50 | always_fail×29 | 1.0000 | not_estimable（不可估（簇数不足）） | 0.0000 | 0.0000 | 0 |
| split | trajectory_comprehensive | 0.10 | threshold:0.95×29 | 0.9375 | [0.7692, 1.0000] | 0.2812 | 0.0625 | 0 |
| split | trajectory_comprehensive | 0.25（主值） | threshold:0.95×29 | 0.9375 | [0.7692, 1.0000] | 0.2812 | 0.0625 | 0 |
| split | trajectory_comprehensive | 0.50 | threshold:0.85×1, threshold:0.9×28 | 0.5625 | [0.2500, 0.8333] | 0.5625 | 0.4375 | 0 |

**退化警告（必须与上表一起读）**：以下单元只能靠哨兵策略达到目标漏判率 —— merge/trajectory_accuracy/miss_0.10；merge/trajectory_accuracy/miss_0.25；merge/trajectory_accuracy/miss_0.50；split/trajectory_accuracy/miss_0.10；split/trajectory_accuracy/miss_0.25；split/trajectory_accuracy/miss_0.50。
`always_fail` 的 specificity = 1、漏判率 = 0，但它把**全部** human pass 也判 fail（sensitivity = 0）。这不是可用的校准，而是「拒绝一切」的退化解；不得把它的 specificity 当作评分器区分度的证据。

## 4. 硬样本子集（饱和的正面证据）

- 定义（§7 冻结）：human fail ∧ framework passed ∧ accuracy ≥ 2.0 ∧ comprehensive ≥ 0.6。
- **n_traj = 10，n_scenario = 7**。
- 场景：competitive_intelligence, complaint_investigation, month_end_reconciliation, onsite_support_dispatch, order_profit_analysis, pinbench_apm_market_research, vip_ticket_escalation。
- 逐轨迹理由类别、轨迹证据与 grader 原话摘录见 `reports/failure_taxonomy.md`；含 trace_id 的明细只在本地 `reports/phase4_hard_samples.json`（**不入库**）。

## 5. 混合评分（可执行检查 + LLM judge）的证据

- human fail **16** 条，覆盖 **11** 个独立场景；human pass 32 条。
- **判读：漏判集合不重合** —— framework 与 grader 的漏判集合不重合（存在一方抓到而另一方漏掉的轨迹）。
- 判读规则：PREREG_v2 §7b：支持=漏判集合不重合且并集更优；反对=framework 误杀更多或增益不抵误杀。
- **报告口径限制**：owner 2026-11-14 裁定（PREREG_v2 §12 CC-1）：并集增益与任何比例不得进入结论性文字，最多陈述「漏判集合不重合」；计数与率只留在本数据层。
- **判读的效力边界**：以上按 round1 标签原样计算。`reports/failure_taxonomy.md` §4 记录了金标准疑点（其中一条同时落在 Phase 3 注入池内），§6 说明硬样本中有条目无法干净地计为评分器漏判。因此该观察建立在含未裁定疑点的标签上，owner 裁定前不得升级为确认性结论。
- 抓到数、漏判率、误杀数与并集增益只保留在 `reports/phase4_calibration.json` 的 `hybrid_scoring` 数据层，按上述裁定**不进入**本报告的结论性文字。

## 6. 限制（只写真实的）

- 单一 judge 模型（deepseek-flash）、`thinking=off`、`direct`、repeat 0、未防御臂；标签来自单一标注者的 round1，**闸门 A 未通过**。
- 独立场景 28 个（merge）；hard sample 只有 7 个场景。
- 阈值网格与目标函数在 §7/§7b 冻结，**未**在看到结果后调整；本阶段全部 exploratory。
- comprehensive 分数顶格（v1 最低 0.6354、100% ≥ 0.6）：降低阈值换召回必然牺牲 specificity，校准不能凭空创造区分度。
- 新增 API 调用 **0**，新增花费 **$0.00**；原始输出全部由 `.cache/llm` 离线恢复并通过 token+分数身份校验。

## 7. 复算

```bash
.venvs/judge/bin/python scripts/phase4_analysis.py --resamples 2000 --seed 0
.venvs/judge/bin/python -m pytest tests/test_calibration.py tests/test_phase4_analysis.py
```
