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


---

## D15 S4 按当前源码修正 Claw-Eval 接入前提（2026-11-04）

**证据**：侦察绑定 Claw-Eval 提交 5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7；完整报告在 notes/claw_eval_recon.md。本关只读源码、batch --help 与静态清单，没有任务/服务/容器/LLM 运行。

**修正**：显式 --config 可使用任意路径/文件名；config.yaml 仅是默认搜索名。原生 trace schema 有 8 类事件，正式分数在后追加的 grading_result，trace_end 的分数默认值不当标签。原生 JSONL 缺少初始 system 消息，S5 需保存实际请求/system sidecar，S6 缺失时标记而不猜造。general 标签的 199 个任务中 38 个还带 user_agent，余下 161，与 README 分组可对齐。

**安装建议修正**：D1 的 non-editable 方案不能单凭安装方式保证 peer grader 路径可用或构建不写源目录。当前 load_peer_grader 的默认 tasks 根依赖源码位置；S5 建议独立 claw 环境安装依赖，显式只读源码路径导入，使两个英文候选能找到中文 peer grader。不改上游、不混装 judge/claw；本关只新建空的独立 claw venv 执行标准库 CLI help，实际接线和安装在 S5 落实。

**接线要求**：原生 provider 默认 streaming，judge 最多 31 次循环且某些任务直接调用 judge.client。当前共享 client 只支持非流式，因此 S5 的本地 provider/SDK 接线须覆盖全部调用、在 spawn worker 中生效、禁止额外付费重试并记录非流式偏差。只替换 YAML 或 judge.evaluate 不符合统一封装要求。预算拒绝时停止批次，不借 native catch/retry 继续调用。

---

## D16 S4 提交可审查的 S5 两任务建议（待用户确认，2026-11-04）

**建议而非已执行决定**：T010_contact_lookup 与 T002_email_triage，各 trials=1、parallel=1、Docker sandbox，单任务独立 trace base，先 contact 后 email。其 JSON fixtures 存在、无模拟用户/实时搜索需求，且能覆盖工具往返。T091/T096 的附件当前缺失，不能把 tools=[] 当成可直接运行的纯对话任务，也不生成替代数据。

**成本建议**：agent thinking off、上限1024；Claw 原生 judge 按既有 D6 保留默认 thinking、上限8192。预计两任务约 $0.03–0.10，条件性工程预算预留 $0.75；这要求 S5 先实施统一封装、请求额度/输入估计/尝试次数限制，并仍受累计 $3 总预算约束。它不是原生 Claw 的费用上界，本关没有任何新模型消费。未经用户确认不启动 S5。

**评估边界**：task_score 为 safety*(0.8*completion+0.2*robustness)，communication 不参与当前公式；原生 robustness 是工具错误恢复，不是跨 trial 稳定性。DeepSeek 官方框架评分不能称为榜单官方 Gemini/Claude 标签；单次 trial 不称为 Pass³。沿用既有 judge-thinking 方案 A；达到预算/账单未知就停止，不擅自切换另一思考设置来继续。


---

## D17 S5 按已确认两任务实施 worker 接线（2026-11-04）

**授权**：用户在 S4 报告后“继续”，确认 T010/T002、各 trials=1/parallel=1、agent thinking off、Claw judge 默认 thinking on、$0.75批次预留且累计不超$3。未添加第三任务、人工标签、稳定性或注入实验。

**实现**：本项目 ClawSession/native_bindings 与顶层 bounded_worker 在 macOS spawn 子进程内安装局部绑定。保留上游消息转换、response解析、run_task、服务/沙箱和任务grader；替换 provider 的实际网络路由为共享非流式 LLMClient。LLMJudge 及 T002 直接 judge.client 路径均受控，不只包 evaluate。上游构造出的未使用 SDK 客户端立即关闭；真实网络只有共享封装。SDK重试禁用，封装最多3次；原生31次循环不能产生额外付费请求。

**拒绝策略**：S5Stop 是专用 BaseException，避开上游广泛的 except Exception 重试/吞异常；worker/ServiceManager/Docker context 的 finally仍清理。输出截断/过滤、未知字段、请求额度、账本未知、预算拒绝立即停批次，不改评分以求通过。停机时原生TraceEnd可能缺失，sidecar/manifest记录 stopped；不补造成功事件。

**额度**：agent保留15/20轮，单输出1024；judge每任务最多1个逻辑请求、输出8192，thinking保留默认effort（不偷换成OpenJudge的off设置）。worker共享同一账本，串行执行；累计ceiling=min(3,运行前累计保守费用+0.75)。native batch输出仍保留，已存在pilot manifest拒绝额外trial/覆盖。

**输入预检修正**：带原生sandbox工具集合的首个请求保守估计约22552/22932，S4暂定16000不成立。保留工具与提示集合，将单请求拒绝阈值改为48000估计输入，不截断内容。未提高资金预算；S4的“最坏情况约0.735美元”条件式不再当作当前费用上界，按每次实际请求预留并允许提前停止。真实调用前已向用户说明。

**明确偏差**：DeepSeek替换官方模型、仅1trial、agent关闭thinking/输出1024、保留Claw judge默认thinking/8192、非流式替代流式、60秒网络超时代替provider300秒、统一三次重试和额度、ERROR_RATE=0显式保留mock实现默认。Docker按原生Dockerfile构建，保留原工具集合；记录image ID。所有偏差进入pilot manifest/README/日志。

---

## D18 S5 轨迹、system sidecar 和测量解释（2026-11-04）

**决定**：以TraceStart实际UUID绑定每个worker的请求sidecar，记录原始model请求body（包含真实system prompt），不记录SDK headers或api_key字段。正式分数来自native grading_result/batch_results，不从缺省TraceEnd推断。原始usage/响应保留共享账本与忽略缓存，rawtrace/sidecar也本地忽略，S6再制作所需脱敏golden样例。

**实际结果**：T010=0.8040、T002=0.8500，均1次trial；9个真实completion（7agent+2judge）、无重试、无400。S5合计38728输入/2161输出，保守峰值费用$0.014212；阶段累计39725输入/2268输出，$0.014640。这是两条mock环境真实执行轨迹的接通证据，不是可靠性/增益或统计显著性结论。

**账本优先**：T002 native judge_calls为空，但共享账本实记1次judge调用，说明不能用native call_log估计总成本。两个grading_result的efficiency字段为0，是CLI追加事件时只复制四个评分维度所致；真实轮数和耗时取TraceEnd/batch trial。S6保留这些原始字段及差异，不静默覆盖。

**只读/密钥验证**：运行前后全上游文件SHA-256无变化，git status干净；容器/服务已按原生context清理。实际API key值在S5输出、共享usage及响应缓存中命中0文件。无新直接依赖；Claw环境单独装上游host requirements（含mock/Docker依赖），未安装OpenJudge。

---

## D19 S6 无损 adapter 与真实结构 golden（2026-11-04）

**决定**：OpenAI messages 是源轨迹的评分视图；metadata按事件序号完整保存所有原始event及完整请求sidecar，另外保存event→messages映射、未映射内容、tool.name来源、system来源与完整grading_history。取最后grading_result，不将TraceEnd默认0作为标签。工具调用ID必须唯一、每个结果恰好匹配一次；无法映射的内容保留并标记，runner拒绝对语义不完整视图调用模型。完整适配轨迹单独落本地JSON，评分JSONL引用其路径和source SHA-256，避免每行重复大量原文。

**system恢复**：仅从实际UUID相同的S5首个agent请求恢复真实system；缺失时adapter明确标missing，S6 pilot入口拒绝运行，不拼造官方提示。tool.name从对应assistant.tool_use.name补齐，参数JSON字符串与原生provider一致；reasoning_content原样保留。is_error、audit_snapshot、tool_dispatch、计时/usage、未支持blocks等全部保留在原事件metadata，不声称它们都进入每个原生grader提示。

**golden 来源**：T010/T002 的本地轨迹用于建立原生消息结构参考。公开测试副本保留消息角色、事件顺序及工具调用配对，提示词、回复及工具数据使用合成内容。原始轨迹和 sidecar 保留在本地，公开样本仅用于结构回归测试。

---

## D20 S6 原生评分结果的完整性与成本（2026-11-04）

**评分**：串行运行2个LLM trajectory graders和2个只接收messages的规则grader；不引入新依赖。OpenJudge提交写入每行。规则行judge_model/thinking为null、usage全0；LLM行明确deepseek-flash、thinking=false，与S5保留thinking=true的Claw judge区别记录。实际API usage和缓存逻辑usage分开，回放不累计新费用。

**严格校验理由**：原生Accuracy会将越界分数clamp到1–3；原生Comprehensive callback会把无有效step转换成0。本地模型子类改为先校验原始上游Pydantic schema，再调用原callback；runner另核对原始score、finish_reason、step数量和唯一连续索引，拒绝截断/漏步/重复索引，不放宽断言来适配模型输出。错误用status=error、score=null，非数值0；每行立即checkpoint，transport/账本错误停批次。该校验是本地运行行为差异，上游文件和原生评分公式不改。

**step定义与局限**：Comprehensive按assistant含tool_calls的一整轮计step，不按单个工具调用；T010为2轮/2调用，T002为3轮/8调用，要求覆盖索引0..N-1。其四维raw分1–5，整体由原生公式归一化0–1；Accuracy为1–3，不能直接和Claw task_score求差。原生Comprehensive提取提示时丢弃system文本，故该分不能证明system遵从；原始system仍保留在adapter与metadata。两个规则使用Jaccard词重叠与原生threshold1.0/0.5，不代表语义信息增益或任务正确性。

**预算**：4次真实completion预计30000输入、8192输出上限，峰值估算$0.018831；批次预留$0.15且累计不超$3，每请求仍预留重试费用。实际14339输入+606输出，4次请求、无重试，保守费用$0.005029；阶段累计54064输入+2874输出、$0.019668。S6输出已存在则拒绝再次付费执行，--offline复用响应缓存。只完成S6，不提前创建S7报告或阶段二实验。

---

## D21 S7 离线回放后生成确定性 v0 报告（2026-11-04）

**授权与取舍**：用户在S6完成后“继续”，按原始S7计划完成报告与验收。沿用当前已确认的工作目录/分关单提交约定，不额外切换分支或要求重复批准。选择先用同一请求参数从缓存重放原生四grader，再报告；不只复制旧分数文件，不使用脱敏golden替代实验，不新增真实模型调用。直接scripts/report.py保留为仅渲染已有分数的入口。

**报告契约**：按native TraceStart真实UUID连接manifest/原生grading_result/四grader行，每条pilot轨迹始终保留一行。重复/外来/冲突provenance拒绝；缺失或错误分数显示MISSING/ERROR并使报告INCOMPLETE，不替换为0、不从分母删掉。表中保留各自量纲，Claw列明确是本次DeepSeek重跑的框架分，不称榜单官方Gemini/Claude标签；不计算小样本相关性或人工一致性。

**成本与确定性**：费用只由共享账本非cached completion计算，模型发现排除；原始paid usage可按S2/S3/S5 agent/S5 judge/S6区分。缺账本直接失败；未知价格/usage或.pending记账标记使总额UNKNOWN、状态不完整，不能冒充0费用。表中分组独立向上取六位，阶段总额从未四舍五入的明细独立计算，不能简单求已取整行之和。报告时间与digest来自原始paid证据，排除不断变化的缓存回放时间/重复账本行；因此同一证据重复make phase1内容一致。用临时文件后原子替换报告；命令非零时旧报告不当作本次成功证据。

**实现边界**：scripts/run_phase1.py只启动score_trajectories.py --offline与report.py，遇非零停止，无付费回退、无Claw重跑；schema/step不合格仍保留S6错误行。本关只用标准库与现有usage/YAML模块，不新增依赖。README重写目标/三问/Mermaid/固定commit/独立venv/离线和live区别/局限。

## D22 S7 可迁移证据与干净克隆验收（2026-11-04）

**路径修正**：S5原始manifest有绝对路径，直接复制到另一工作树会读取旧位置。新增本地artifact_path仅把outputs后的路径映射到当前项目；当前副本缺失即拒绝，不回退旧工作区，即使旧文件仍存在；符号链接逃逸也拒绝。评分缓存输入保持原文，metadata记录新的本地位置和相同源hash，不改原始trace/sidecar或上游。

**可复现边界**：源码克隆可在装好依赖后离线make test，无.env、原始输出或Docker需求；实际报告重建另需本地S5 rawtrace/sidecar/manifest、原始usage账本、完整.cache/llm三者一起恢复。README给本地备份/新目录恢复命令，不把raw模型文本/响应缓存作为公开Git产物。只有脱敏结构golden和不含原文的数值报告入库。

**验收设计**：在.cache/s7-validation创建不带.env/.venvs/outputs的新Git克隆，覆盖待提交S7文件；两个上游为相同固定版本的只读源码链接。创建全新judge venv、按README安装并跑测试，再只恢复必要证据/缓存，禁socket且去除密钥后make phase1。uv离线安装首次因缓存缺pytest包失败；安装允许访问包索引，不谎称安装离线，离线要求覆盖安装完成后的测试与报告回放。最终结果见notes/log.md。

**S7 审查修复补充**：独立只读审查发现混合model/thinking能被接受、NaN错误分数使digest失败两项P2。先增加7个失败回归，再拒绝混合模型/思考配置与非已审定thinking-off设置；成功模型行须匹配原始s6账本tag/model/thinking/token证据。非有限分在表中继续为ERROR，只在digest编码时转为明确invalid_nonfinite标记，不改分数、不放宽断言。完整104项测试及24项S7定向测试通过。

**S7 实测验收补充**：新克隆新venv测试104 passed（无.env、无outputs、禁socket）；安装上游676个文件前后delta=0。恢复三类本地证据而不恢复已有scores/报告后，禁socket/无密钥make phase1成功；每次4缓存命中、0新增模型请求。重复和跨目录报告SHA-256相同，缺缓存exit2并保留1条error/null行，不更新旧报告或请求网络。阶段19次真实completion、54064输入/2874输出、保守总额$0.019668保持不变。


---

## D23 审计修正：repeat_id 进入缓存键（2026-11-04）

**背景**：RQ2 需要对同一轨迹重复打分；缓存键无重复编号时，重复调用会命中同一条缓存，实验无效。

**决定**：`LLMClient.complete(repeat_id=...)`；非 None 时写入缓存键，None 时键不变（保持阶段一缓存与报告可复现）。`use_cache` 空参数暂保留（有测试守护），`is_error` 暂只留在 metadata、不改动 judge 输入；若 P4/P2 发现工具报错可见性影响评分，再另立决策。仅使用 deepseek-flash，无 pro 价格，故 pro 不进入预算。已删除工具生成的 docs/superpowers。


---

## D24 RQ1 判定阈值预注册（2026-11-04，人工标签产生之前）

- 二分类口径：human/official 的 pass 为正类。
- `TrajectoryAccuracyGrader`：score ≥ 2 判通过（上游量表定义：3 与 2 均“达成任务目标”，仅 2 含多余步骤；1 为未达成）。
- `TrajectoryComprehensiveGrader`：score ≥ 0.6 判通过（连续量表，阈值无上游定义，事先固定，不看标签调参）；同时报告与阈值无关的 AUC。
- 规则型 grader（循环检测、观察信息增益）不是结果型评分，只做探索性 AUC，不做 pass/fail 阈值结论。
- 主配置：deepseek-flash、thinking 关、Direct、repeat 0；其它配置属于 RQ2 分析。
- 指标：准确率、Cohen's κ、PABAK、混淆矩阵、分类别、基线（永远通过/多数类/随机）、95% bootstrap CI（2000 次，固定种子）。官方分部分由 LLM 评分，仅作第二参照。若 κ 在类别极偏时无定义，报告 PABAK 与原始一致率。

## D25 P2/P3 工程决定（2026-11-04）

- Claw 批量运行沿用已审计的 S5 绑定（共享客户端、账本、请求配额），用 profile 取代两任务白名单；agent `max_tokens` 两种配置均为 4096（2048 时有任务被截断，且两配置需一致）。
- 任务选择：确定性分层（hard14/medium16/easy10，种子固定），排除 user_agent、多模态、真实联网/OCR 服务，max_turns≤30；T102_xss_filter 两次跑到 30 轮且 token 失控（单次约 $0.16 未完成），记录后排除。
- LLMClient 改为线程安全（锁、飞行中预算预留、引用计数式 pending 标记），为 P3 并发；仍不支持多个进程同时写同一账本（pending 标记会互相阻塞——保守行为，已确认）。
- 账本对账：一次 agent 请求失败（15.7 秒无响应、状态未知）使累计成本变为“未知”并按设计阻止后续请求。已将该行以保守上界（重试请求的 prompt token + 4096 输出）改为 `unknown_reconciled` 并保留原行于 outputs/usage/reconciliation.jsonl；供应商控制台为准。
- 上游发现（供 P5）：OpenJudge `TrajectoryAccuracyGrader` 将模型输出分数钳制到 [1,3]（99 变 3），空消息返回 0.0（超出量表）；我们在 `judging.check_raw` 里重新解析原始输出，把钳制视为无效行而非有效分。
# D26 Recovery and annotation freeze (2026-11-05)

The current owner authorizes free continuation, not paid historical roadmap
caps. No batch will run until a new explicit stage budget is approved.
Request sidecars override stale D25 prose: four cap cohorts exist (off2048=4,
off4096=47, on4096=27, on16384=9). Preserve them and treat thinking comparisons
as confounded. Freeze 50 blind traces before human labels, retaining all six
framework failures; the failure-enriched sample is not population-representative.
Use complete annotation text, atomic CSV saves, no overwrites, and fresh blind
repeat ids after >=2 days. Never infer, suggest or fill owner labels.

# D27 Reproducible stage runs and lexical controls (2026-11-05)

Use `scripts/experiment.py` as the canonical P2 judge/P3/P4/probe entry point.
Historical stability/probe scripts delegate to it. Run manifests bind exact
messages, model, generation configuration and OpenJudge commit; per-job atomic
records are authoritative, JSONL is a recoverable projection. Resume preserves
the original absolute spend ceiling rather than adding a new cap each invocation.
Error rows remain null and retry through the same completion cache. A stale
exclusive run lock requires inspecting processes, not blind deletion.

Bootstrap by task id, keeping on/off trajectories and paired repeats together.
Output variation alone cannot establish whether temperature was honored. Official
scores never substitute for owner labels. Information-gain's lexical score can
change under benign text insertion; report changes rather than demanding an
unaffected rule control. Formal P4 is gated on complete owner labels and budget.

Verified pro pricing is kept in `configs/pricing_p3.yaml` to preserve the historical
phase1 pricing checksum. Source: https://api-docs.deepseek.com/quick_start/pricing/ .
Verified 2026-11-05; pro peak input miss/output $1.32/$3.96 per million, off-peak
$0.66/$1.98. This is planning support, not authorization for pro calls.

# D28 Unknown billing remains unknown; budget reservations are separate (2026-11-07)

Two legacy P2 transient attempts have no provider usage but have successful
same-request retries in cache. Do not rewrite those original ledger rows or set
usage_known=true. Reconstruct the exact request offline from the frozen run plan
and cached retry; attach an external overlay keyed by the entire ledger record's
fingerprint. Use request UTF-8 byte count +4096 and the full output cap, priced at
the larger recorded/current rate, as a conservative budget reservation.

`summarize.cost_usd` remains null for unknown actual accounting. `budget_cost`
is a separate, explicitly labeled spending guard that includes every reserved
attempt. Unmatched/malformed reservations and missing successful-response usage
remain fail-closed. Future transport-uncertain attempts record their request bound
at failure, never invented token usage. This follows the existing request guard's
bound, not the smaller successful-retry token estimate.

The original P2 absolute ceiling stays $3.500680. Probe has its own approved
$0.20 cap, starting only after P2, using reservation-inclusive budget accounting.
No original approval is renewed or enlarged. Independently reviewed; 173 offline
tests pass, including unknown accounting staying unknown and budget exhaustion
still blocking requests. Offline reconstruction appends cache-hit ledger entries;
original ledger bytes remain an unchanged prefix. No labels/upstream edited.

# D29 P4 cohort from submitted labels (2026-11-10)

The owner stopped the first annotation round at 48/50. P4 can explicitly
require two blanks with `--expected-unlabeled 2`. The default requires zero
blanks. The planner and report both reject a count mismatch and use the
actual owner failure labels. Two blank items remain outside the cohort.
The current cohort has 16 human failures. The rule-only subset report
uses existing rows for the same cohort. The paid P4 run awaits approval.
