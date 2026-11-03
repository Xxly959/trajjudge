# 设计决策记录

每条决策记录：背景 → 决定 → 理由 → 影响。阶段二若推翻某条，在新条目里引用旧编号，不删除历史。

---

## D1 上游只读，覆盖配置放在本项目

**背景**：`../OpenJudge` 与 `../claw-eval` 是上游克隆，需要把两者的模型都指向 DeepSeek，但直接改上游会让结论无法复现、也无法对比原始行为。

**决定**：不修改上游任何文件。DeepSeek 的模型配置以 `configs/claw_eval_deepseek.yaml`（S4/S5 落地）形式放在本项目，通过 `claw-eval --config` 传入。确实必须改上游时，先停下来询问并记录在本文件。

**理由**：评审者能用 `git -C ../claw-eval status` 验证上游未被污染；偏差来源可枚举。

**影响**：`uv pip install ../claw-eval` 采用非 editable 安装，避免在上游目录生成 `*.egg-info`；OpenJudge 按 S3 要求 editable 安装，若上游出现构建产物需在日志中说明。

---

## D2 judge 与 claw 各自独立虚拟环境

**背景**：OpenJudge 要求 Python >=3.10（本项目按 3.10–3.12 使用），Claw-Eval 要求 >=3.11；两者依赖树重叠但不应互相污染。

**决定**：`my-project/.venvs/judge`（3.12，装本项目 + OpenJudge）与 `my-project/.venvs/claw`（3.12，装 claw-eval）。`make test` / `make phase1` 使用 judge venv；跑 Claw-Eval 用 claw venv。

**理由**：符合“各项目独立虚拟环境、不要混装”；也把“评分侧依赖”和“被测框架依赖”分开。

**影响**：Makefile 显式指定解释器路径，脚本不依赖 `source activate`。

---

## D3 模型 id 不在代码里写死

**背景**：DeepSeek 的模型名会变，旧名（deepseek-chat / deepseek-reasoner）已不可用；凭记忆写死会导致后续全部失败。

**决定**：`configs/deepseek.yaml` 的 `models.judge` / `models.agent` 默认为 `null`；S2 通过 `/models` 接口列出真实 id 后再回填。`load_settings()` 在模型名为空时抛 `ConfigError` 并提示去跑探针。

**理由**：把“确认事实”变成流程的一部分，而不是一次性的手工动作。

**影响**：S1 阶段 `make test` 不依赖真实模型名（测试用临时配置）。

---

## D4 所有 LLM 调用走同一封装，缓存键覆盖全部可变输入

**背景**：预算有限，且要求“缓存命中时不得发请求”。

**决定**：`trajjudge.llm.LLMClient` 统一负责请求、重试、缓存、usage。缓存键 = SHA-256(canonical JSON)，输入包含模型 id、messages、生成参数、tools、thinking 开关与缓存格式版本号。

**理由**：thinking 开关与 tools 会改变输出，必须进键；版本号让缓存格式升级时自然失效。

**影响**：`use_cache=False` 可强制联网（探针需要），但依然记 usage。

---

## D5 成本：没有价格就不编价格

**背景**：预算约 3 美元，但本阶段尚未确认 DeepSeek 当前定价页的数值。

**决定**：`configs/pricing.yaml` 的条目允许为 `null`。有价格时 `summarize()` 给出美元金额；任一无价格模型出现时 `cost_usd=None` 并在报告中列出 `unpriced_models`。

**理由**：宁可报告“未知”，也不要把记忆里的价格当事实写进报告。

**影响**：成本汇总在 S2 回填价格后才给出金额；token 数始终可用。

---

## D6 grader（judge）的 thinking 关不掉，先接受并记录

**背景**：claw-eval 的 `ModelConfig` 支持 `extra_body`，但 `JudgeConfig` 只有 `api_key/base_url/model_id/enabled`，`LLMJudge.__init__` 也只接收这三个参数，请求里写死 `temperature=0, max_tokens=8192`。因此**配置层无法给 grader 关闭 thinking**。

**决定**：阶段一采用方案 A —— 接受 grader 带 thinking 运行，如实记录 usage 与偏差；若成本超限再切换到方案 B（本项目内 `claw_bridge` 包装 `LLMJudge` 注入 `extra_body`，仍不改上游文件）。

**理由**：方案 A 不改变上游行为，结论更容易解释；judge 调用是单轮、无 tools，不存在 reasoning_content 回传的 400 风险。

**影响**：grader 的 output token 会显著高于非 thinking 情况，`notes/claw_eval_recon.md` 的成本估算必须按带 thinking 计。报告“已知问题”需写明：官方榜单用 gemini-3-flash / claude-opus-4.6，本项目改用 DeepSeek，分数不可与榜单直接比较。

---

## D7 adapter 不允许静默丢弃字段

**背景**：Claw-Eval 轨迹是 Anthropic 风格 content blocks（text / tool_use / image / audio / video …），OpenAI messages 只有 text + tool_calls + tool 消息。

**决定**：`adapt_trace()` 返回 `AdaptedTrace(messages, metadata)`；任何无法映射的事件或 block 进入 `metadata`（按事件序号索引），并在 runner 的 JSONL 里带出计数。

**理由**：静默丢弃会让“评分差异”与“数据丢失”无法区分，直接毁掉研究结论。

**影响**：多模态任务的 block 会以 metadata 形式保留，阶段一优先选择纯文本 general 任务。

---

## D8 密钥策略

**背景**：仓库可能公开。

**决定**：`.env` 进 `.gitignore`（`.env.*` 也忽略，白名单 `.env.example`）；`.env.example` 使用 `<your-deepseek-api-key>` 占位符，刻意不含 `sk-` 前缀；`tests/test_no_secrets.py` 在每次 `make test` 时扫描 git 跟踪文件中的 `sk-...` 形态密钥，并校验 `.env` 确实被忽略。

**理由**：把“提交前检查”变成自动断言，而不是靠记性。

**影响**：新增任何含密钥的样例必须先脱敏。
