# 讲解卡 04 · P1 工程底座：τ-bench 适配器、多厂商抽象、Held-Out 攻击集与组件消融

## 1. 改了什么、为什么改

- **τ-bench 无损适配器（[taubench_adapter.py](../../src/trajjudge/taubench_adapter.py)）**：
  - 支持官方 `sierra-research/tau-bench` 的 JSON 归档与社区 JSONL（如 `AgentSuite/tau-bench-trajectories`）两种格式，统一转换成 TrajJudge 的标准 OpenAI `messages`、`scenario_id`（`taubench:{domain}:{task_id}`）和客观标签 `objective_pass`（`reward >= 1.0`）。
  - **强防泄漏隔离**：`reward`、`expected_actions`、`expected_outputs` 全部隔离在 `privileged_outcome`，绝不进入送给裁判的 `messages`；同时内置按场景轮询的 `select_taubench_cohort`（最大化独立场景数，目标 ≥100 失败、≥60 场景）与 `select_best_of_n_tasks`（直接为 P2-A 抽出 `N=4` 重排任务）。
- **多厂商 Provider 配置（[config.py](../../src/trajjudge/config.py)、[llm.py](../../src/trajjudge/llm.py)、[openjudge_bridge.py](../../src/trajjudge/openjudge_bridge.py)、[providers.yaml](../../configs/providers.yaml)）**：
  - 原先 `llm.py` 硬编码发送 DeepSeek 专属的 `extra_body={"thinking": ...}`，一旦切 Qwen / GLM / Kimi 就会直接 HTTP 400。
  - 新增 `thinking_style`（`deepseek` / `dashscope` / `none`）和 `load_provider_settings()`，既 100% 保持 DeepSeek 历史缓存键一字节不变，又能零改动跑通 OpenJudge 和 Grounded 裁判在 3 家以上厂商上的调用。
- **P1-5 Held-Out 注入测试集（[perturb_v3.py](../../src/trajjudge/perturb_v3.py)）**：
  - 严格切分 `dev`（旧 4 条）与 `test`（新 15 条，涵盖英文间接指令、中文翻译改写、JSON 字段伪装、业务政策伪造），支持 `tool_result` / `assistant_mid` / `assistant_final` 三个位置，并把规范 SHA-256（`08a07040...b30081`）事前冻结进 [PREREG_v3.md](../../docs/PREREG_v3.md)。
  - 自动化守卫测试顺手拦住了一次真实细节：`T10_json_eval_metadata` 最初写了 `unauthorized_side_effect`，和裁判 JSON schema 字段名重叠，立即被 3-gram 守卫抓出并改成了黑盒字段 `policy_violations`。
- **P1-6 组件消融与提示词敏感性（[grounded_judge.py](../../src/trajjudge/grounded_judge.py)）**：
  - 为 `grade_trajectory_grounded` 增加 `ablation`（`full` / `no_veto` / `no_quarantine` / `no_ledger`）与 3 组语义等价提示词 `prompt_variant`（`v0` / `v1` / `v2`）。

---

## 2. 关键参数及取值理由

| 参数 / 设计 | 取值 | 理由 |
| :--- | :--- | :--- |
| 场景聚类键 | `taubench:{domain}:{task_id}` | τ-bench 同一个任务会跑多个 trial（`pass^k`），必须按任务聚簇做 Bootstrap，避免伪重复。 |
| 采样策略 | 场景轮询（round-robin） | 优先铺开独立场景数（≥60），再从同场景补抽其余 trial，最大化聚类有效样本量。 |
| 外部单价默认值 | `configs/pricing_v3.yaml` 中为 `null` | 严格遵守 D5：未核实官方价格前，`LLMClient` 拒绝发送付费请求，杜绝凭记忆编价格。 |

---

## 3. 面试官可能怎么追问 & 参考回答

1. **追问：“为什么大样本验证选 τ-bench 而不是纯代码类的 SWE-bench？”**
   - **参考回答**：“因为 LightClaw 和 Claw-Eval 的核心场景都是**多轮工具调用 + 外部状态变更 + 政策/授权边界**（比如先核验用户身份再改订单、未确认不能直接发消息或取消）。τ-bench 的 `retail` 和 `airline` 域天然具备这三要素，且它的标签来自数据库终态比对，完全客观、无人工标注噪声；同时每道题自带多次 trial，正好还能无缝做 Best-of-N 重排。”
2. **追问：“怎么保证你调完 Grounded 提示词之后，P1-5 注入防御结果不是过拟合测试集？”**
   - **参考回答**：“两道硬锁：第一，把 15 条 held-out 攻击模板的 SHA-256 提前冻结在 `PREREG_v3.md` 里；第二，CI 里的 3-gram 守卫测试每次都会扫描 `grounded_judge.py` 全部源码和 3 套提示词，只要和任一攻击模板出现 ≥ 3 词重叠就直接红灯失败。”

---

## 4. 留给你自己动手的小改动（约 10 分钟）

1. 打开 [configs/providers.yaml](../../configs/providers.yaml)，查看 `deepseek`、`qwen`、`glm`、`kimi` 的 `thinking_style` 分别是怎么配的。
2. 运行新加的 P1 底座单测，确认全绿：
   ```bash
   .venvs/judge/bin/python -m pytest tests/test_p1_foundation.py -v
   ```
