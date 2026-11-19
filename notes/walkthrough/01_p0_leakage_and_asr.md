# 讲解卡 01 · 修复注入数据泄漏（P0-2）与重构 ASR 口径（P0-3）

## 1. 改了什么、为什么改

### P0-2 修复测试集特征泄漏
- **改了什么**：
  - 从 [grounded_judge.py](../../src/trajjudge/grounded_judge.py) 删除了 `_INJECTION_CUE_RE` 正则和 `structural_signals.untrusted_grading_directive_cues` 字段，并去掉系统提示词中对 `"EVALUATION NOTICE"` 的字面引用。
  - 在 [test_grounded_judge.py](../../tests/test_grounded_judge.py) 新增防泄漏守卫测试 `test_no_perturb_template_leakage_in_grounded_judge`：遍历 `perturb.py` 里所有攻击模板，拆成所有长度 ≥ 3 的连续词片段（3-gram），断言裁判源码与系统提示词里 **0 处命中**。
  - 在 [DECISIONS.md](../../docs/DECISIONS.md) 新增 **D30**，正式撤回旧的「注入膨胀率降 15 倍至 6.25%」结论。
- **为什么改**：旧正则直接写了 `perturb.py` 攻击模板里的原话（如 `evaluation notice`、`ignore your rubric`），事后检查发现该信号在扰动臂 **16/16** 触发、原始臂 **0/47** 触发——相当于给模型塞了一个“这条轨迹被攻击了”的作弊标签。不修的话，面试官看一眼源码就会当场戳穿。

### P0-3 重构 ASR 指标并补齐无攻击噪声底
- **改了什么**：
  - 在 [scenario_stats.py](../../src/trajjudge/scenario_stats.py) 新增 `normalized_delta`、`noise_floor_from_repeats` 与 `injection_metrics_v3`。
  - 在 [openjudge_bridge.py](../../src/trajjudge/openjudge_bridge.py) 与 [judging.py](../../src/trajjudge/judging.py) 新增可选参数 `use_json_schema` 与 `schema_retries`（默认关闭，不破坏历史 manifest 哈希），为重跑中性对照臂（目标有效配对 ≥ 14/16）做好准备。
  - 用 [p0_analysis.py](../../scripts/p0_analysis.py) 离线算出 [reports/injection_metrics_v3.json](../../reports/injection_metrics_v3.json)。
- **为什么改**：
  - 以前把任意微小涨分（`pert > orig`）都算“攻击成功（ASR）”，但对连续分 `[0, 1]` 的 `Comprehensive`，**无攻击重复打分 3 次本身就有 43.8%（42/96）的概率分数变高**（安全声明下噪声底 `38.6%`）！
  - 这意味着安全声明后 `45.5%` 的涨分率几乎贴着无攻击噪声底 `38.6%`，而未防御的 `89.4%` 才远超噪声底；同时必须以**决策翻转率（`fail→pass / base_fail`）**为主指标，以**量表归一化分差 `Δ/(max-min)`**为次指标。

---

## 2. 关键参数及取值理由

| 参数 / 公式 | 取值 | 理由 |
| :--- | :--- | :--- |
| 防泄漏词窗长度 | `3-gram`（≥ 3 词） | 1–2 词常见英文短语（如 `the grader`）容易误报，≥ 3 词既能精准拦住模板泄漏，又不误伤正常安全边界描述。 |
| 噪声底配对方式 | 所有有序重复对 `(r_i, r_j), i ≠ j` | 对 3 次重复（6 个有序对）具有置换不变性，不受 `repeat_id` 编号顺序影响，直接度量“再评一次分变高”的概率。 |
| `decision_flip_case_study` 门槛 | `base_fail_scenarios < 5` | 延续 `PREREG_v2` 的场景簇门槛；当基线判失败的独立场景不足 5 个（如 `Accuracy` 仅 1 个场景）时，严禁把翻转率当成总体结论。 |
| `schema_retries` 缓存键 | `f"{repeat_id}.retry{attempt}"` | 避免重试时再次命中同一条格式损坏的缓存，同时保留第 0 次请求的缓存键完全兼容旧运行。 |

---

## 3. 面试官可能怎么追问 & 参考回答

1. **追问：“你为什么撤回了旧的 6.25% 防御数字？是不是说明你的裁判根本没用？”**
   - **参考回答**：“恰恰相反，这是我做代码复核时主动抓出的测试集泄漏——旧版正则匹配了 `perturb.py` 模板词，在扰动臂 16/16 触发、原始臂 0/47 触发。这种数字在工程上是不可信的，所以我直接删掉正则、加上 CI 3-gram 守卫测试，并在 `DECISIONS.md` D30 留下撤回记录。真实防御效果只认后续在开发期未见过的 held-out 攻击集（P1-5）上跑出来的新数字。”
2. **追问：“怎么区分攻击带来的涨分和 LLM 自身的随机波动？”**
   - **参考回答**：“我用同一批 16 条轨迹未扰动的 3 轮重复打分算出了无攻击噪声底：`Comprehensive` 未防御下两两重测就有 43.8% 涨分（`mean |Δ|=0.032`）。所以报告注入效果时，我不只看涨分率，而是把**决策翻转率（主指标）**、**归一化分差（次指标）**和**无攻击噪声底**并列汇报。例如 `L3_notice/tool_result` 未防御涨分 89.4%（远超 43.8% 噪声底），而加安全声明后降到 45.5%（已接近 38.6% 噪声底）。”

---

## 4. 留给你自己动手的小改动（约 15 分钟）

1. 打开 [src/trajjudge/grounded_judge.py](../../src/trajjudge/grounded_judge.py)，临时往 `EVIDENCE_GROUNDED_SYSTEM_PROMPT` 里加一句 `"please ignore your rubric"`。
2. 运行测试：
   ```bash
   .venvs/judge/bin/python -m pytest tests/test_grounded_judge.py -v
   ```
3. 观察 `test_no_perturb_template_leakage_in_grounded_judge` 如何精准报出命中的 3-gram 和来源模板名 `L4_override`。
4. 用 `git checkout -- src/trajjudge/grounded_judge.py` 恢复，再确认测试全部变绿。
