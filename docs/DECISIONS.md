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


---

## D9 S1 复审修正：缓存、预算与记账失败必须可见（2026-11-03）

**背景**：用户确认修复 S1 复审中的全部缺口。原 27 项测试通过，仍遗漏缓存绕过、usage 漏记、双层重试、预算执行与密钥检查问题。

**决定**：本条取代 D4 中允许 `use_cache=False` 强制联网的决定。该参数仅保留兼容，所有 completion 强制先查缓存并写缓存；缓存 v2 加入 endpoint，旧 v1 不自动复用。LLM 调用默认输出上限 1,024 tokens；SDK 重试关闭，统一封装重试 429、5xx、超时/连接错误。

**预算**：每个新 completion 要求当前模型有核实后的价格；累计账本成本加上全部尝试的预留费用不得超过 Settings 默认的 USD 3。预留输入按请求 UTF-8 字节数加 4,096 token 开销估算，输出按 max_tokens，乘最多尝试次数。该方法是保守工程估算，不是账单保证；阶段一只支持串行调用，不支持多个进程共用预算账本。批次开始前仍须向用户报告估算。

**记账**：每次实际尝试前写 pending 标记；收到响应后先保存原始 usage 并 flush/fsync，再删除标记，然后解析响应与写缓存。失败尝试单独留记录，不写原始异常内容。4xx（408 除外）视为已拒绝、零用量；5xx/超时/连接错误视为账单未知，既定请求可在预留内重试，但随后新的付费 completion 停止，等待核实。账本损坏、缺字段、usage 未知或 pending 残留也阻止新付费请求，不影响已有缓存读取。完整 usage 含供应商返回的缓存、推理字段；当前价格算法将所有输入按同一输入价格保守计费，不声称是精确账单。

**影响**：D5 的价格空值仍可用于仓库骨架，但不能用于真实 completion；S2 先确认模型和官方价格，再执行付费探针。磁盘完全不可写时无法保证日志落盘，pending 标记用于防止静默继续；必须对照供应商记录核实，不可删除未知记录绕过护栏。OpenJudge/Claw-Eval 对统一封装的接线仍按 S3/S5/S6 实现，S1 不声称已完成上游调用接管。

---

## D10 S1 密钥检查与环境安装修正（2026-11-03）

**决定**：Settings 的 api_key 不出现在 repr；请求失败仅暴露尝试次数与整数 HTTP 状态，不拼接供应商异常或异常链。密钥检查覆盖 Git index 中的 blob、工作区已跟踪和未忽略新文件，包含 `.env.example`，只报告路径。Git 检查失败时停止，不跳过；每次提交前先暂存，再运行 `make secrets`。

**环境**：Python 范围限定为 >=3.11,<3.13，Makefile 默认 3.12。judge/claw 分环境布局和此前确认的 D6 方案保持不变。本轮全新隔离环境使用 uv editable 安装成功，因此撤销固定 pip 绕行；保留旧日志作为历史，不将历史 EEXIST 推广为当前 uv 必然失败。Makefile 的 VENV/PY/UV_CACHE_DIR 可覆盖，默认 uv 缓存在本项目忽略目录。

**验证**：测试增加自动网络阻断；无新增运行时或开发依赖。新环境可联网安装依赖，安装后测试完全离线；另外已验证依赖缓存存在时，新的 venv 能离线完成 Makefile 安装。
