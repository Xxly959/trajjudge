# 讲解卡 02 · 同误杀率对比（P0-4）与离线 Veto 归因（P1-6 离线）

## 1. 改了什么、为什么改

### P0-4 在相同误杀率下公平比较裁判
- **改了什么**：
  - 在 [calibration.py](../../src/trajjudge/calibration.py) 新增纯 Python、零第三方依赖的 `roc_curve_fail`、`pr_curve_fail`、`recall_at_fpr`（同时给出严格保守的 `step` 与线性插值 `interpolated`）以及精确双尾 `exact_mcnemar` 检验。
  - 在 [p0_analysis.py](../../scripts/p0_analysis.py) 计算全部 6 个评分器在 `v1 / v2 / round2` 三套标签下的 `Recall@FPR=10%/20%`、`PR-AUC`（附 2000 次场景簇 Bootstrap 95% CI）和配对 McNemar 检验，写入 [reports/same_fpr_comparison.json](../../reports/same_fpr_comparison.json)。
  - 在 [generate_figures.py](../../scripts/generate_figures.py) 新增图 5 [fig5_roc_pr_same_fpr.svg](../../reports/figures/fig5_roc_pr_same_fpr.svg)，并**顺手修了一个隐藏 Bug**：旧代码读 `phase4_calibration.json` 时写错了键名 `variants`（真实键名是 `calibration.merge.graders`），导致一直回退到硬编码数字，把 LOSO 均衡校准的**漏判率 62.5%（10/16）**误写成了**误杀率 62.5%**（实际均衡误杀率是 `5/32 = 15.6%`，而 `miss ≤ 25%` 目标下误杀率高达 `23/32 = 71.9%`）。
- **为什么改**：
  - 以前把默认阈值下 `Comprehensive`（`0/14` 召回、`0%` 误杀）直接和 `Pro Grounded`（`3/14` 召回、`9.4%` 误杀）比较，其实不在同一个工作点上！
  - 拉平到同一个误杀率 `FPR = 10%` 后，真相立刻浮出水面：**在这 48 条探索性人工标签上，`Grounded` 并没有超过重新设阈值的 `Comprehensive`**（插值召回 `22.0%` vs `42.9%`；`PR-AUC` `0.375` vs `0.558`；默认阈值配对 McNemar `p = 0.250` 不显著）。照实写出来，反而最能体现工程与统计学功底，也直接论证了为什么下一步必须上 P1-1 大样本客观标签并改进打分连续性。

### P1-6 离线组件审计（零成本）
- **改了什么**：统计已有 `109` 条有效 Grounded 评估（Flash 原 47 + 扰 16 + Pro 原 46）中 `veto_overrode_model` 与 `structural_veto` 次数，写入 [reports/veto_ablation_offline.json](../../reports/veto_ablation_offline.json)。
- **发现了什么**：**`veto_overrode_model = 0/109 (0.0%)`**，`structural_veto = 0/109`。说明当前样本上 Grounded 相对原生提示词的变化全部来自审计提示词和账本义务拆解，代码侧 Veto 还没在真实冲突场景里被触发过。

---

## 2. 关键参数及取值理由

| 参数 / 设计 | 取值 | 理由 |
| :--- | :--- | :--- |
| ROC / PR 正类定义 | `fail`（`not truth_pass`），分值取 `-score` | 评测场景最关心“抓坏轨迹”，以失败为正类时 `FPR = 正常轨迹误杀率`、`TPR = 失败召回率`，与业务直觉完全一致。 |
| 并列得分（Tie）处理 | 相同分值合并成同一 ROC 步进，并列报 `step` 与 `interpolated` | `Accuracy` 只有 `{1,2,3}` 三个离散值，`Grounded` 分数也高度集中。若随意拆开并列点会凭空造出乐观曲线；合并步进 + 同时报保守/插值两个值才诚实。 |
| `exact_mcnemar` 算法 | `math.comb` 精确二项分布双尾检验 | 样本量小（`b + c ≤ 6`）时卡方近似会失真，精确二项分布对任意小样本都严格准确，且零外部依赖。 |
| `FPR` 锚点 | `10%` 和 `20%` | 工业回归门禁通常最多容忍 10%–20% 的人工复核误报率，高于 20% 就没有落地价值。 |

---

## 3. 面试官可能怎么追问 & 参考回答

1. **追问：“你算完同误杀率发现 Grounded 反而打不过调阈值后的 Comprehensive，那你这个设计还有意义吗？”**
   - **参考回答**：“非常有意义，这个反直觉结果帮我精准定位了两个问题：第一，`Grounded` 当前的打分公式把所有通过样本压在 `1.0`，几乎没有排序分辨率（所以 ROC/PR 曲线吃亏），而 `Comprehensive` 靠步骤均分保留了一定的连续排序信号；第二，当前 48 条轨迹只有 14 条失败，而且人工复测 `κ=0.250`，配对 McNemar `p=0.25`，统计检验力严重不足。所以下一步我们一方面用 τ-bench 客观数据库终态标签把失败样本扩到 ≥100 条，另一方面要针对‘排序分辨率’和‘未授权写操作’优化 Grounded 的连续打分与证据校验。”
2. **追问：“你离线查出来 Python Veto 覆写率是 0/109，那代码侧 Veto 是不是多余的？”**
   - **参考回答**：“在当前这批 Claw-Eval 轨迹里它确实没有触发过覆写——这正好说明离线做组件归因有多重要，不能拍脑袋宣称‘是 Veto 带来了提升’。但从系统防御角度，代码侧 Veto 属于**确定性安全兜底（fail-closed invariant）**：比如工具调用没有匹配返回、没有最终回复，或者模型把某条义务标成 `omitted` 却在最后手滑写了 `verdict: pass`，哪怕只占 1% 的线上长尾，确定性门控也能保证不漏网。真正要量化它的边际收益，需要 P1-6 的 4 组完整消融。”

---

## 4. 留给你自己动手的小改动（约 15 分钟）

1. 打开 [scripts/p0_analysis.py](../../scripts/p0_analysis.py)，把 `fpr_targets=(0.10, 0.20)` 改成 `fpr_targets=(0.05, 0.10, 0.20)`。
2. 运行：
   ```bash
   .venvs/judge/bin/python scripts/p0_analysis.py
   ```
3. 打开 [reports/same_fpr_comparison.json](../../reports/same_fpr_comparison.json)，看看在极严格误杀率 `FPR = 5%` 时，`Comprehensive` 和 `Pro Grounded` 各自的 `recall_step` 与 `recall_interpolated` 变成了多少。
4. 看完后把 `scripts/p0_analysis.py` 改回 `(0.10, 0.20)` 并重跑一次。
