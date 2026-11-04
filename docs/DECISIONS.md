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


---

## D11 S2 模型选择与探针范围（2026-11-04）

**背景与证据**：用户本轮明确要求使用 deepseek-flash。先通过统一客户端请求模型列表，实际返回 deepseek-flash、deepseek-v4-pro 后才回填配置。agent/judge 两个角色都记录选择的 ID，尚未执行对应上游接入。

**决定**：只使用 deepseek-flash。S2 为普通对话、thinking off/on 和一次本地工具调用往返，共 5 次 completion；输出上限分别为 64、64、1024、1536、1536。thinking 显式传 enabled/disabled，开启时使用 reasoning_effort=low，所有生成参数与工具策略参与缓存键。工具续答仍携带 tools，并设置 tool_choice=none 限制为一次工具调用；上一轮 reasoning_content 逐字回传。本关不发送故意缺失 reasoning 的负向真实请求，不据此声称验证了供应商错误分支。

**理由**：用最小可检查的固定答案验证接口接通、模式切换及正确的工具往返。低 thinking effort 是成本选择，与默认 high 的差异必须记录；这不是 judge 质量或研究效果证据。

**官方来源**：
- https://api-docs.deepseek.com/guides/thinking_mode/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/api/list-models/

**缓存与离线**：模型列表是无生成 token 的元数据请求，也在统一封装中缓存、重试并写 usage（endpoint=models）；汇总时单独排除其费用。--offline 禁止创建 SDK/发请求，缓存缺失即失败，load_settings 可在该模式不要求密钥。在线和离线的摘要分别写入不同的本地输出文件，完整结果追加 notes，缓存不入 Git。

---

## D12 S2 价格与成本记法（2026-11-04）

**来源**：https://api-docs.deepseek.com/quick_start/pricing/ ，本轮通过官方页面核实。deepseek-flash 每百万 token 的高峰价格：输入 cache miss $0.30、输入 cache hit $0.006、输出 $1.20；低峰对应 $0.15、$0.003、$0.60。

**决定**：配置保存完整价格信息，现有预算/汇总继续统一按高峰输入 cache miss 与高峰输出价格保守计算，不冒充精确账单，不依赖运行时段或假期判断。供应商原始 usage 保留在本地账本，包括 prompt-cache 明细。探针还加上不超过累计预算的 $0.05 批次预留；运行前打印约 5,000 输入 + 4,224 输出 tokens 的 $0.006569 估算。

**影响**：估算大于实际 token 对应金额不表示计费异常；应清楚标注保守估算。若供应商调整价格，下一次真实批次前重新核实。S2 本次真实 493 输入、69 输出 tokens，保守费用 $0.000231；不将后续缓存回放算作新增模型消费。


---

## D13 S3 保持原生 OpenJudge 调用链并统一记账（2026-11-04）

**证据**：源码 openjudge/models/openai_chat_model.py 的构造函数接受 api_key/base_url，未传时读取 OPENAI_API_KEY/OPENAI_BASE_URL；**kwargs 存到 self.kwargs 后合并到 achat 的 SDK 参数。因此 extra_body 可透传。本轮真实天气调用中，SDK 请求体观察到 thinking.type=disabled，供应商没有返回 reasoning_content。

**决定**：本项目的 DeepSeekOpenJudgeModel 继承上游 OpenAIChatModel，通过原生 achat 与 SDK 处理请求/结果。自定义本地 SDK HTTP transport 接收序列化 JSON，再交给统一 LLMClient；它不打开第二条网络路径、不记录请求头。统一封装扩展 response_format 参数（进入缓存键）并缓存完整供应商 JSON，用于原生 SDK 离线回放。只支持串行、非流式调用，未识别参数报错而不静默丢弃。

**JSON 差异**：LLMGrader 默认传 Pydantic structured_model，原生模型会请求 JSON Schema；DeepSeek 当前官方接口只列 text/json_object（https://api-docs.deepseek.com/api/create-chat-completion/）。本地子类改成 json_object，随后仍按原来的 Pydantic callback schema 本地校验，避免缺失 score 被默认值掩盖。评分提示和上游 grader 实现不变。这是显式响应格式适配，不声称“未改变原生运行行为”；未额外发送 Schema 负向真实请求。

**结果**：无需关闭 thinking 的替代方案；本轮已验证 extra_body 的实际请求路径。score=3 仅为官方玩具样例的真实模型输出，既不是人工标签，也不是一致性/稳定性/抗注入证据。额外预算采用 $0.02 批次预留，仍计入累计 $3。

---

## D14 S3 editable 安装不得污染上游（2026-11-04）

**决定**：make install-openjudge 使用 scripts/install_openjudge.py。先按上游 pyproject 声明安装运行依赖，再对 ../OpenJudge 单独执行 uv pip install --no-deps -e；该第二步用 DIST_EXTRA_CONFIG 将 setuptools egg_info/build 目录指到本项目 .cache/openjudge-build。全程关闭 Python 字节码写入，上游文件的安装前后 SHA-256 指纹必须一致。

**原因**：首次把重定向环境作用于整组依赖，jieba/rouge-score 共享 build 目录而发生构建冲突；已改为分两步。失败尝试及成功安装均核对上游文件变化为 0，不删除或修改上游来解决问题。direct_url.json 确认 editable=true，openjudge.__file__ 指向真实 ../OpenJudge。

**依赖理由**：pandas/NumPy/SciPy/scikit-learn 等由 OpenJudge 自身声明，属于用户要求的真实 editable 安装所需运行依赖，仅装在 judge 环境；不添加其 dev/训练 extras。本项目没有新增直接依赖。SDK transport 复用当前 OpenAI SDK 对应的 httpx/httpx2，不额外创建独立 HTTP 依赖。Makefile 导出 PYTHONDONTWRITEBYTECODE=1，README 的直接命令也须遵守这一上游只读边界。


**S3 记账补充**：本轮累加实际多条 usage 时发现二进制浮点会把 $0.0004275 汇总为 $0.000427。已先用 S2/S3 两组用量补回归复现，再改为标准库 Decimal 累加、最终六位小数向上取整，保持费用估算的保守含义；不增加依赖、不改变原始 token 记录。早期日志摘要作为历史保留，最终摘要为 $0.000428。
