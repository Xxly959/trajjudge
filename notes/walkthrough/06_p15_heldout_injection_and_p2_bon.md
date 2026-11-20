# 讲解卡 06：P1-6 提示词稳定性、P2-A Best-of-4 重排与 P1-5 15 模板 Held-Out 防注入

> **对应里程碑**：D33（`reasoning_effort=low` + Markdown 代码块 JSON 剥离修复）· P1-6 提示词敏感性（`v0/v1/v2`）· P2-A Best-of-4 重排闭环 · P1-5 Held-Out 15 模板三臂注入对比

---

## 1. 改了什么与为什么改（What & Why）

1. **真实工程排障（[D33](../../docs/DECISIONS.md)）**：
   - `glm-5.3-flash` 设置 `reasoning_effort="low"` 后，约 `40/200` 条 `Comprehensive` 有效响应会在外层包上 ```` ```json ... ``` ```` 代码块；上游 OpenJudge 的 `repair_and_load_json` 正常解析并写入缓存，但本地 `judging.py` 直接调原始 `json.loads` 报错丢弃，外加高并发触发 `504`。我们在 [llm.py](../../src/trajjudge/llm.py) 新增 `parse_json_object` 仅剥离外层 Markdown 代码块（内部字段缺失/钳制分数仍由 `check_raw` 和 `validate_and_score_grounded` 严格拦截），并把并发降为 `--workers 4`，**零额外 API 费用从缓存直接恢复这 40 条样本**。
2. **P1-6 三套等价提示词敏感性**：
   - 验证在 60 条分层 τ-bench 上把审计 prompt 改写成 3 种不同措辞（`v0 / v1 / v2`），`ROC-AUC` 分别为 **`0.9103 / 0.8952 / 0.8936`**（均值 **`0.8997`**, 标准差仅 **`0.0092`**），`PR-AUC` 均值 `0.8846`（SD `0.0148`），`R@10%` 均值 `74.1%`（SD `2.75%`）。这直接证明架构效果稳健、不是在某一句魔法词上过拟合。
3. **P2-A Best-of-4 重排闭环与「缺失幸存者偏差」发现（负结果与设计局限）**：
   - 在 `50` 个 τ-bench 任务（每任务 4 次采样，其中**仅 `25` 个混合成败任务能区分选法**）上，随机选通过率 **`42.0%`**，末轮语气启发式仅 **`40.0%`**，`Evidence-Grounded`（`44/50` 完整任务）为 **`45.5% (20/44)`**（整体为零效应负结果，不写入简历正面贡献），数据库 `oracle` 为 **`72.0% (36/50)`**。
   - 一个非常值得讲的统计细节：`OpenJudge Comprehensive` 在其 `32/50` 完整任务上表观通过率达 `53.1% (17/32)`，表面看起来比 `Grounded (45.5%)` 高——但查明原因是因为 `Comprehensive` 在另外 `18` 个难题上 `504`/Schema 报错被丢掉；把两者放到 **`28` 个共同完整任务** 上对齐对比，两者完全打平为 **`16/28 (57.1%)` vs `16/28 (57.1%)`（Exact McNemar `p = 1.0`）**！同时诚实看到：即使较好的单轨迹裁判，在“同题 4 选 1 难题”上仍距离数据库 `oracle` 差 `26.5 pp`。
4. **P1-5 Held-Out 15 模板间接提示注入（`exploratory`，替代已撤回的 D30 `6.25%`）**：
   - 因仅 `12` 条失败轨迹 / `8` 个独立场景且 CI 高度重叠（外加中转站审计 `relay_audit.json` 查出 `p15` 中 `5/675` 次请求被静默路由至 `nvidia/nemotron-3-ultra-550b-a55b`），本项严格定性为 **`exploratory`**——方法论价值在于主动发现并撤回旧泄漏结论、再用 15 个冻结未见模板重测，方向一致但样本量不足以下确认性结论（不放入简历数字）：
     - **`Evidence-Grounded full`**（`237` 有效配对 / `12/12` `orig0`）：`tool_result` 翻转率 **`10/134 (7.5%)`** `[0.6%, 18.5%]`，全部位置 **`18/214 (8.4%)`**；涨分率 `20.1%` 低于无攻击噪声底 `26.4%`；JSON 字段伪装攻击翻转仅 **`2/57 (3.5%)`**。
     - **`Grounded no_quarantine`**（移除 `<untrusted_tool_data>` 隔离槽，`91` 配对 / `9/12` `orig0`）：`tool_result` 翻转率方向上升至 **`7/55 (12.7%)`** `[0.0%, 30.4%]`，且全实验全部 7 次翻转均源自 `tool_result`；JSON 伪装翻转 **`3/19 (15.8%)`**；无攻击重复决策翻转噪声底从 `3.2% (2/62)` 升至 **`12.5% (4/32)`**。
     - **`OpenJudge Comprehensive`**（`195` 配对 / `11/12` `orig0`）：因打分饱和仅 `1` 个场景基线 `<0.60`，`tool_result` 涨分率达 **`55.7% (68/122)`**（噪声底 `47.6%`），中文改写注入引起正向漂移 **`+0.0175 [+0.004, +0.039]`**。

---

## 2. 关键实现与数据源（Key Files）

- [src/trajjudge/llm.py](../../src/trajjudge/llm.py)：`parse_json_object`、`reasoning_effort` 配置透传与缓存键隔离
- [src/trajjudge/perturb_v3.py](../../src/trajjudge/perturb_v3.py) & [scripts/run_p1_heldout_injection.py](../../scripts/run_p1_heldout_injection.py)：15 模板冻结 Test 集与 `compute_p15_arm_summary`
- [scripts/run_p2_best_of_n.py](../../scripts/run_p2_best_of_n.py)：Best-of-4 重排与配对 McNemar 计算
- 跟踪产物：[reports/p16_ablation.json](../../reports/p16_ablation.json) · [reports/p2_best_of_n.json](../../reports/p2_best_of_n.json) · [reports/p15_heldout_injection.json](../../reports/p15_heldout_injection.json) · [reports/figures/fig7_p15_injection_and_p2_bon.svg](../../reports/figures/fig7_p15_injection_and_p2_bon.svg)

---

## 3. 面试高频追问与参考应答（Interview Follow-ups）

1. **Q：Best-of-4 里 `Grounded` 只比随机高 `3.5 pp`（`45.5%` vs `42.0%`），和 `Comprehensive` 在共同 28 题上也只是 `57.1%` 打平，这算失败吗？为什么会这样？**
   - **A**：不算失败，而是一个很扎实的边界发现。二分类场景里（区分明显成功 vs 明显失败），`Grounded` 的 `ROC-AUC = 0.755` 显著甩开 `Comprehensive (0.628)`；但 Best-of-4 的决定性战场只在那 `25` 个混合题里（其中 4 个候选都在处理同一复杂政策），许多失败是“模型以为客户已经隐式同意但数据库字段差一个参数”，没有环境执行结果时任何无特权文本裁判都很难区分同题中的“差一点就对”和“真的做对”。这恰恰说明**为什么生产闭环需要把轻量规则 + 轨迹裁判 + 可执行 Verifier 结合，而不能把无执行校验的 LLM-as-a-Judge 当万能 Oracle**。
2. **Q：为什么同样在 `p2bon` 里 `Comprehensive` 表观 `53.1%` 高于 `Grounded` 的 `45.5%`，你们还敢把表观数字放进报告？**
   - **A**：因为我们没有只放表观数字——我们第一时间查出了 `Comprehensive` 只完成了 `32/50`（含 9 个全对简单题），而 `Grounded` 完成了 `44/50`（同样只有 9 个全对简单题，多覆盖了 12 个更难的混合/全败题）。只要按统计规范在 **`28` 个共同完整任务上做配对比较，两家都是 `16/28 (57.1%)`（`p = 1.0`）**。这种“识别非随机缺失引起的幸存者偏差”反而是评测工程师的核心基本功。
3. **Q：Held-Out 注入里，`full` 在 `tool_result` 还有 `7.5% (10/134)` 翻转，为什么做不到 `0%`？**
   - **A**：因为我们移除了针对已知攻击短语的规则作弊（D30 撤回），新结果来自完全未见过、且伪装得像真实业务系统的 15 类注入（比如 `[CRM_SYNC] Prior verbal authorization...` 直接在对话里伪造业务侧前置授权）。相比关闭隔离槽的 `12.7%`（其中 JSON 伪装 `15.8%` vs `3.5%`），隔离槽已经拦截了结构化伪装并把涨分率压到噪声底（`20.1% < 26.4%`）以下；剩余 7.5% 来自纯语义伪装“已口头确认”的边界案例，这也界定了仅靠单轮隔离槽提示词的真实安全上限。
4. **Q：如果面试官问你在 `p2bon` 修了 JSON 代码块解析问题后，怎么保证没有放水放进非法分数？**
   - **A**：`parse_json_object` 只做一件事：剥离最外层三引号 ```` ```json ... ``` ````；剥离后依然要原封不动过两道刚性结构校验——OpenJudge 的 `check_raw`（校验每一步 `step_index` 连续不重不漏、四维分数必须是 `1..5` 整数）和 Grounded 的 `validate_and_score_grounded`（校验每条义务状态、索引范围和 Veto 门控），里头只要缺字段或越界照样报错记为 `status="error"`。

---

## 4. 3 分钟动手小练习（Hands-on Exercise）

在本地断网运行下方脚本，亲自验证 P2-A「幸存者偏差 vs 共同对齐」以及 P1-5 三臂在不同攻击类别（`json_disguise` / `policy_spoof` / `en_directive` / `zh_paraphrase`）上的翻转率差异：

```bash
cd my-project
python3 - <<'EOF'
import json
p2 = json.load(open("reports/p2_best_of_n.json"))
print("P2-A marginal:", {k: (v["n_tasks"], v["pass_rate"]) for k, v in p2["selectors"].items()})
print("P2-A paired 28:", p2["mcnemar_pass_rate"]["trajectory_comprehensive|glm-5.3-flash_vs_evidence_grounded|glm-5.3-flash"])

p15 = json.load(open("reports/p15_heldout_injection.json"))["arm_summary"]
for arm in ("evidence_grounded|defended=True", "evidence_grounded|defended=False"):
    print(f"\n=== {arm} ===")
    for cat, st in p15[arm]["by_category"].items():
        print(f"  {cat:16s}: flip={st['fail_to_pass_count']}/{st['base_fail_pairs']} ({st['decision_flip_rate']}), inf={st['score_inflation_rate']}")
EOF
```
