# TrajJudge 轨迹数据工程实施计划

**核对日期** 2026-11-11  
**目标** 把单来源评分审计扩展成可构建、核查和复用的 Agent 轨迹数据工程。  
**架构** 复用 Claw-Eval 适配和盲标工作流。数据层区分任务、运行、环境结果和各来源的评分。用一小批公开运行验证跨来源适配，再用原创任务展示可执行验收和训练数据筛选。  
**工具** Python、JSONL、pytest、现有 Makefile。原创任务优先本地 pytest，随后验证 Harbor 包装。

配套 [分阶段提示词](2026-11-11-trajjudge-data-prompts.md)。下文的阶段目标是待实施内容。

## 已复核的现状

| 事实 | 对质量的影响 |
| --- | --- |
| v1 导出 87 条轨迹、51 个任务，含 48 条人工判定、100 条 OpenJudge 评分。报告哈希与 JSONL 匹配，任务 ID 零交叉，全量测试 181 项通过。 | 当前快照能构建，关联结果可核对。 |
| 用纯合成数据删除一条已冻结的源轨迹后，构建退出码为 0，报告显示缺少 1 条冻结样本，缩水产物替换了原有产物。 | 文件内容被改动会触发哈希检查，文件丢失却走普通排除分支。冻结证据缺失必须使正式构建失败。 |
| 回顾性 eval 为 10 个任务、17 条轨迹，其中 6 条人工通过、2 条人工失败、9 条未标。当前只按任务 ID 拆分，重复统计只查同题的完全相同消息。 | 可验证分组行为。2 条人工失败不足以稳定估计失败召回，跨题近重复和同源变体仍需核查。 |
| Claw-Eval 的导出判定只有 passed/task_score。 | 已关联三种判定。独立可复验的环境产物是下一项数据能力。 |

审查入口为 [当前构建脚本](../../../scripts/build_dataset.py)、[合成端到端测试](../../../tests/test_dataset.py)、[适配器](../../../src/trajjudge/adapter.py)、[实验口径](../../RESUME_NOTES.md) 和 [数据发布边界](../../THIRD_PARTY.md)。原始轨迹和盲标材料保存在本地。

## 调研选型

| 一手资料 | 方法 | TrajJudge 落点 |
| --- | --- | --- |
| [Anthropic · Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | 区分任务、尝试、交互记录和环境最终状态。程序检查可客观验证的结果，主观评审另做人工校准。 | 轨迹与结果证据分开。将「声称已完成但没有正确产物」设为原创题负例。 |
| [SWE-bench 评分实现](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/grading.py) · [公开运行归档](https://github.com/SWE-bench/experiments) | 将修复目标与回归行为分开测。公开提交可关联预测补丁、测试日志、结果和轨迹。 | 选 SWE-bench/experiments 为第二来源。只接一份公开提交，小规模离线导入。 |
| [OpenAI · Verified 审计](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) · [Pro 审计](https://openai.com/index/separating-signal-from-noise-coding-evaluations/) · [Scale · Pro V2](https://labs.scale.com/blog/swe-bench-pro-v2) | 测试可能拒绝功能正确的解，公开解答可能被模型见过。Pro V2 对改写题面做独立盲读，在干净环境复评。 | 独立正确解与局部错误解一起检验验收脚本。公开 SWE 样本只做适配验证，不能证明模型水平或训练无污染。 |
| [Terminal-Bench 4.1](https://www.tbench.ai/news/terminal-bench-4-1) · [Harbor](https://docs.harborframework.com/tasks/overview) · [ATIF](https://docs.harborframework.com/agents/atif) | 提交产物与 verifier 版本分离，旧产物可复评。ATIF 提供跨工具的轨迹格式。 | 原创题保存产物、验收版本和结果。接通第二来源后，按字段映射评估 ATIF 导出。 |
| [SWE-smith](https://github.com/SWE-bench/SWE-smith) · [训练轨迹数据卡](https://huggingface.co/datasets/SWE-bench/SWE-smith-trajectories) · [SWE-rebench V2](https://github.com/SWE-rebench/SWE-rebench-V2) | 可执行任务和可验收轨迹是训练数据的来源。构建环境与筛选轨迹属于数据生产。 | 用原创题演示筛选及导出，记录每条样本的验收证据。 |

同时对照了 [Microsoft SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live) 的任务更新和提交时间限制，以及 [Google DeepMind gbench 的 Pro V2 说明](https://github.com/google-deepmind/gbench/blob/main/docs/evals/swe_bench_pro.md) 的数据集版本、镜像与复评配置。首版采用轻量的公开产物导入和本地原创任务，减少多套运行环境的维护成本。

## P0 · 修正导出契约和质检

**落点** 优先修改 scripts/build_dataset.py 和 tests/test_dataset.py，沿用 adapter.py、artifact_path 与标签校验。

- [x] 先用合成回归测试覆盖冻结源文件缺失、sidecar 缺失、JSONL 损坏、哈希改变、冻结 ID 消失或重复。正式构建对这些情况非零退出，保留最后一份有效产物。普通未完成运行仍按原因排除。
- [x] 增加数据版本与输入指纹。让 JSONL、报告和指纹组成一个可识别的完整快照；测试中断和报告与数据不匹配。保留 make dataset 入口，说明迁移方式。
- [x] 报告按 split 统计任务数、轨迹数、人工覆盖和正负例、评分缺失或异常、重复及排除原因。核对当前 87/51、48、100、6 与零任务交叉，变化逐条解释。
- [x] 交付可脱离本地盲标材料运行且产物可查看的原创合成示例。全量测试、真实本地构建、两次重建一致、公开示例字段检查全部通过。

**验收** 当前静默缩水可复现，修复后失败可诊断且有效快照仍可读。

**证据** [P0 验收记录](2026-11-11-trajjudge-data-p0-verification.md)。

## P1 · 接入公开 SWE 轨迹与结果

**输入** [SWE-bench 官方组织的 mini-SWE-agent 公开运行](https://github.com/SWE-bench/20260902_mini-v2.4.6_gemini-3-5-flash/tree/8dcca98587e7f698753903e3b1747eb5dc013cb1)，固定 revision 为 8dcca98587e7f698753903e3b1747eb5dc013cb1。GitHub 文件树显示 264 个轨迹目录下的文件，以及 258 个同时有 report.json、patch.diff 和压缩测试日志的实例目录。两个数量不同，按 instance_id 查交集后再选 6–10 个样本，尽量包含通过和失败。调研只核对了文件清单，尚未下载样本或解析结果。根目录未见许可文件，实施时先核对素材权利，公开示例只用自造数据。

- [x] 支持一种具体的提交格式。记录来源、revision、文件角色、SHA-256。用合成夹具覆盖错误匹配、缺件和来源 ID 碰撞。公开演示使用结构等价的自造夹具；上游文件按许可处理。
- [x] 用命名空间区分来源。共用 task、trial/transcript、outcome、judgments 四个逻辑对象，保留任务版本、harness、来源类型、任务族、结果状态和证据引用。上游结果记录是否在本项目重新验证。
- [x] 报告来源内覆盖和排除、外部字段映射及重复候选。用仓库、任务族、时间核查隔离；同源同题和衍生变体同组，未知显式标记。Claw-Eval 与 SWE 分列汇总。
- [x] 增加一页数据卡，交代用途、来源、覆盖、排除、命令和限制。附可追查证据的自造样例。

**验收** 现有输入可离线转换，样本能追到固定 revision、轨迹和结果文件。缺失和不匹配可重现，外部接入不改变原 P2 统计。

**证据** [P1 数据卡与验收](../../SWE_IMPORT.md)。

## P2 · 两道原创任务和独立验收

| 任务 | 必须核验的结果 | 回归行为 |
| --- | --- | --- |
| A · 轨迹事件汇总 | 有重复投递、超时重试和乱序事件时，按题面计算最终状态和唯一事件数。 | 单次成功、空输入和固定输出字段。 |
| B · 评分结果关联 | 对重复运行和缺失结果按任务、运行和评分器版本正确关联；缺失报告为 unknown。 | 输入顺序变化时结果一致，原有合法结果语义不变。 |

- [x] 每题提供起始版本、可见题面、固定环境、参考解和验收。测试与可见要求逐条对应。至少有一个失败转通过测试，并保留原有通过测试。
- [x] 在干净工作区跑四种提交：起始实现失败、参考解通过、独立正确解通过、局部错误解失败。固定输入重复运行并记录结果，候选提交与验收文件分别管理。
- [x] 保存结果产物、逐项验收、验收版本和实现来源。手写示范标为人工构造，真实模型跑次有独立记录。Harbor 包装未实测时，标明本地执行范围。

**验收** 首题四路证据齐全后再扩第二题。用具体案例区分产物有误、验收写错和基础设施异常。

**证据** [P2 原创任务与验收](../../ORIGINAL_TASKS.md)。

## P3 · 从原创任务筛选后训练数据

- [x] 先按任务族指定用途，再从分配给训练的原创任务中筛选通过验收的完整示范。四路验收是在测 verifier 的行为。预留给模型评测的任务及变体单独保存。同题、同环境、目标一致且行为结果能解释优劣时才生成偏好对；没有合格样本就报告排除原因。
- [x] 导出版本化的 SFT 和偏好候选，保留来源 ID、验收版本和选择依据。检查目标训练器能读取格式，记录工具调用兼容性。隔离用于评测的公开题及同任务族变体。[TRL 数据格式](https://huggingface.co/docs/trl/dataset_formats)
- [x] 数据卡分别统计人工构造、合成夹具、真实运行。对照只看最终回复的筛选与依据实际结果的筛选，用同一批样本说明差异。

**验收** 每个入选样本都能说明为何符合条件。格式验证和训练收益分别报告。

**证据** [P3 候选数据卡和筛选验收](../../TRAINING_CANDIDATES.md)。

建议分三个迭代：P0 先修正确性，P1 验证第二来源，P2 的第一题连通 P3 最小导出后扩第二题。作品集交付复现命令、数据卡、质检报告、跨来源样例与原创任务验收记录。
