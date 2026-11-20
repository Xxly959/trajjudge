# 讲解卡 05：P1 客观标签 τ-bench 主实验反转、D31 多轮排障与四路组件消融

> **对应里程碑**：P1-1（200 条 τ-bench 客观标签全量对比）· D31（多轮终止态与政策截断修复）· P1-3（跨厂商特权银标盲区审计）· P1-4（两厂商复现与自评偏好检查）· P1-6（四路组件单调消融）

---

## 1. 为什么做这一步（What & Why）

在 P0 阶段我们诚实暴露了一个残酷事实：在 48 条人工盲标 Claw-Eval 队列上（人工双轮 `κ = 0.250`），`EvidenceGroundedGrader` 在同误杀率 `FPR = 10%` 处尚未反超重设阈值的 `Comprehensive`（`22.0%` vs `42.9%`），且代码 Veto 覆写为 `0/109`。如果不换更大规模、无主观噪声的客观基准，这套架构就没有立得住的实证支撑。

本阶段我们切换到 **200 条数据库可执行校验的 τ-bench 多轮工具轨迹（100 失败 / 100 通过、131 独立场景、DeepSeek-V3.2 与 GPT-4o 精确 50/50 平衡）**，并完成 4 路组件消融与跨厂商盲区审计，结果实现了决定性验证：

1. **D31 真实工程排障（面试高频加分点）**：首次在 τ-bench 上跑 Grounded 时，旧版 `has_final_assistant_reply` 假设最后一条消息必须是 `assistant`，导致以 `user` `###STOP###`（170/200）或 `transfer_to_human_agents`（27/200）收尾的轨迹 **161/161 全被 `structural_veto` 误杀**；同时 6KB 业务政策在 1,500 字符处被截断。修复多轮终止态、保留完整政策（上限 7,000 字符）并加入 `confidence_pass` 连续排序后，架构真实表现才得以稳定显现。
2. **P1-1 与配对 `ΔAUC` 口径**：`Evidence-Grounded (glm-5.3-flash)` 在排序能力上显著优于 `OpenJudge Comprehensive`（配对 `ΔAUC +0.156 [+0.053, +0.260]`、`p = 0.001`；ITT 口径 `+0.121 [+0.023, +0.214]`、`p = 0.012`）。相对 `OpenJudge Accuracy`（Flash `0.686` / Pro `0.703`），主要差异在于**把判定点推向高召回区**（抓出约 `+37 pp` 失败、代价是误杀增加约 `+18–22 pp`）及提供可调连续阈值与可审计证据；GLM-Flash complete-case 下有排序提升迹象（`ΔAUC +0.064`, `p = 0.024`），但在 ITT（`+0.045`, `p = 0.184`）、GLM-Pro（`-0.016`）和 DeepSeek-Flash（`ΔAUC = 0.000`）上并未拉开显著的排序差距。注意默认阈值 Exact McNemar（`p < 1e-9`）是在不同误杀率下对比的结果，主证据应看配对 `ΔAUC` 与同误杀率召回（详见 [08_paired_auc_and_operating_point.md](08_paired_auc_and_operating_point.md)）。
3. **P1-6 组件消融（共同样本配对）**：在 60 条分层子集（注意该子集本身偏容易，主实验同一批轨迹 AUC 亦为 `0.910`，全量 200 条为 `0.755`）上，complete-case 配对结果显示 **证据账本（`ΔAUC +0.157, p=0.012`）** 与 **隔离槽（`ΔAUC +0.105, p=0.015`）** 贡献显著，**Python Veto 方向为正（`ΔAUC +0.041, p=0.105`）但 CI 跨 0**（详见 `reports/paired_auc_v3.json` 含 ITT 敏感性）。
4. **P1-4 两厂商 200/200 对称复现 + P1-3 盲区候选**：补充运行官方 `deepseek-flash` post-D31 完整 200 条（`Evidence-Grounded 197/200` + `OpenJudge Accuracy 200/200`）后，证实同底座默认阈值失败召回提升 **`+31.6 pp`**（`16/98 → 47/98 = 48.0%`, `p = 7.92e-09`）而**同模型配对 `ΔAUC = 0.000`**（印证判定点移动解释），`unauthorized_side_effect` 精确率跨两厂商保持 **`74%–84%`**（GLM-Flash `27/32 = 84.4%`、GLM-Pro `30/40 = 75.0%`、DeepSeek-Flash `20/27 = 74.1%`），探索性检查中未见明显自评偏倚（`exploratory`，子组各约 50 条未控制难度），同时诚实定位到零推理底座对 7KB 长政策的轻量推理预算敏感性（`DeepSeek-Flash` `AUC 0.629` vs `GLM-Flash` `0.755`）；跨厂商旗舰 `glm-5.3`（Silver Label）另在 `92` 条客观通过轨迹中筛出 **`13/92 (14.1%)`** 疑似盲区（标为 `exploratory`，待人工复核确认，见 `07_blindspot_cases.md`）。

---

## 2. 关键实现与参数（Key Files & Params）

- **多轮终止态与连续分**：[src/trajjudge/grounded_judge.py](../../src/trajjudge/grounded_judge.py) — `_TERMINAL_HANDOFF_TOOLS`、`extract_evidence_ledger`（保留 7KB 业务政策）、`validate_and_score_grounded`（`pass ∈ [0.50, 1.00]` / `fail ∈ [0.00, 0.45]` 严格 Veto 分区）、4 路消融开关 `ablation = full | no_veto | no_quarantine | no_ledger`。
- **实验与产物**：
  - [reports/p1_taubench_eval.json](../../reports/p1_taubench_eval.json)（P1-1 + P1-4 全量 7 个 LLM 裁判含官方 DeepSeek-Flash `197/200` & `200/200` + 2 个规则基线 + 21 组 Exact McNemar + Holm 校正）
  - [reports/p14_cross_vendor_deepseek.json](../../reports/p14_cross_vendor_deepseek.json)（早期 DeepSeek 161/200 pre-D31 离线复核历史归档）
  - [reports/p16_ablation.json](../../reports/p16_ablation.json)（60 条分层 τ-bench 4 路消融）
  - [reports/p13_blindspot_summary.json](../../reports/p13_blindspot_summary.json)（`13/92` 数据库校验盲区汇总）
  - [reports/figures/fig6_p1_taubench_and_ablation.svg](../../reports/figures/fig6_p1_taubench_and_ablation.svg)

---

## 3. 面试高频追问与标准应答（Interview Follow-ups）

1. **Q：为什么早期 48 条 Claw-Eval 上 Grounded 没超过调阈值的 Comprehensive，到了 200 条 τ-bench 上反而全面反超？是不是过拟合了 τ-bench？**
   - **A**：三个客观机制：(1) Claw-Eval 48 条仅 14 个主观人工失败（双轮 `κ = 0.250`），`R@10%` 置信区间宽达 `40–60 pp`，根本缺乏统计检出力；(2) D31 修复了此前截断 6KB 领域政策与缺少连续排序分的问题；(3) τ-bench 是数据库可执行验证的多轮工具变更场景（含明确权限/确认政策），直接对应 `EvidenceGrounded` 的「工具副作用账本 + 越权检测」设计目标，且我们把早期 48 条探索集诚实保留在报告附录 A、不做任何删改。
2. **Q：为什么 `glm-5.3-flash` 在 Grounded 上反而比更大的 `glm-5.3` Pro 校准更好（`AUC 0.755` vs `0.683`，误杀 `25.8%` vs `38.4%`）？**
   - **A**：实测日志显示 `glm-5.3-flash` 平均消耗约 `200` 个轻量推理 token（总输出 `1,511` tokens），而 `glm-5.3` Pro 在 `thinking=disabled` 下零推理 token（总输出 `1,286` tokens）且判断过于激进（误杀率高达 `38.4%`）。这说明在需要逐条对照 6KB 政策核验工具参数的审计任务里，**轻度步骤化推理对校准的帮助大于单纯参数量扩张**。
3. **Q：你们说消融里 `no_quarantine` 即使在没有提示注入的干净 τ-bench 上也掉了 `0.088 AUC`，为什么？**
   - **A**：看 `reports/p16_ablation.json` 的交叉指标就明白了：移除 `<untrusted_tool_data>` 隔离槽后，正常样本误杀率从 `34.6%` 飙到 `44.8%`，同时模型自我矛盾导致 Veto 覆写的比例从 `5.7%` 涨到 `17.2%`。隔离槽不仅是安全边界，也是**结构化语义分隔符**，帮裁判清楚区分“环境返回了什么”和“助手声称了什么”。
4. **Q：P1-4 两厂商（DeepSeek + GLM）完整跑完后，为什么 DeepSeek-Flash (`0.629`) 和 GLM-Flash (`0.755`) 有差距？结论还站得住吗？**
   - **A**：官方 `deepseek-flash` 在 `thinking=off` 下完成了完整 200 条对称运行（`Evidence-Grounded 197/200` + `Accuracy 200/200`，详见 **D34**）。结论很诚实也更有区分度：(1) 同在 DeepSeek 上，通用 `Accuracy` 同样只抓出 `16/100 (16.0%)` 失败，而 `Evidence-Grounded` 把默认失败召回显著提高 **`+31.6 pp`**（`48.0%`, `p = 7.92e-09`）、`unauthorized_side_effect` 精确率 `20/27 (74.1%)`、且排除了自评放水偏倚；(2) 但 DeepSeek (`thinking=off`, 均输出 `740` tok) 比带轻量推理的 `GLM-Flash`（`1,511` tok, `0.755`）甚至 `GLM-Pro`（`0.683`）都更宽松，导致总准确率与低误杀 `R@10%` 排序增益受限——恰恰与消融和 Pro 对比互相印证，说明长政策核验需要底座配足轻量步骤推理预算。

---

## 4. 3 分钟动手小练习（Hands-on Exercise）

在本地免 Key 离线环境下，跑一条命令检查 P1-1 全部配对的 Exact McNemar 检验与 Holm 多重校正，并核对 `fig6` 与 `CLAIMS.md` 是否零误差一致：

```bash
cd my-project
python3 - <<'EOF'
import json
d = json.load(open("reports/p1_taubench_eval.json"))
for name, res in d["holm_fail_recall"]["tests"].items():
    print(f"{name:72s} p={res['p']:.3e}  p_adj={res['p_adjusted']:.3e}  reject={res['reject']}")
EOF
```

观察结果：`glm_pro-accuracy vs glm_flash-accuracy`（`p_adj = 0.501, reject = False`）说明**单纯升级通用裁判模型无显著增益**；`deepseek-evidence_grounded vs deepseek-accuracy`（`p = 7.92e-09, p_adj = 9.50e-08, reject = True`）与全部 GLM Grounded vs 通用裁判对比（`p_adj < 1e-8`）均显著胜出。
