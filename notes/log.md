# 研究日志

记录每个关卡（S1–S7）的：做了什么 / 证据（命令与输出）/ 未解决问题。
只在末尾追加，不修改历史条目。命令输出只摘关键行，API key 一律不记录。

---

## S1 仓库骨架（2026-11-03）

**做了什么**

- 建立 `pyproject.toml`（包名 `trajjudge`，Python >=3.11，依赖仅 `openai` + `PyYAML`，dev 只加 `pytest`）、`.env.example`（占位符不含 `sk-` 前缀）、更新 `.gitignore`（`.env`、`.venvs/`、`.cache/`、`outputs/`、`*.egg-info/`）。
- `src/trajjudge/`：`config.py`（.env + YAML 分层加载，密钥只从环境读）、`cache.py`（SHA-256 内容寻址磁盘缓存）、`usage.py`（JSONL usage 记录 + 成本汇总，价格未知时返回 None）、`llm.py`（统一客户端：429/5xx 指数退避、超时、缓存、usage、`reasoning_content` 回传）、`adapter.py` / `runner.py`（契约 + 占位，S6 实现）。
- `tests/`：27 个离线用例（配置加载、缓存键与命中、重试与快速失败、thinking 参数、assistant 消息回传、usage/成本、密钥扫描）。
- `configs/deepseek.yaml`（模型 id 故意留 `null`）、`configs/pricing.yaml`（价格为 `null`）、`docs/DECISIONS.md`（D1–D8）、`Makefile`（`install/test/secrets/smoke/phase1`）、`README.md`、`scripts/run_phase1.py`（S7 入口占位）。
- 创建 `judge` 虚拟环境：`uv venv --python 3.12 .venvs/judge`（CPython 3.12.13），editable 安装本项目。

**证据**

```
$ uv venv --python 3.12 .venvs/judge
Using CPython 3.12.13
Creating virtual environment at: .venvs/judge

$ make test
.venvs/judge/bin/python -m pytest
...........................                                              [100%]
27 passed in 0.48s

$ git status --short        # .env / .venvs / *.egg-info 均未出现
?? .env.example
?? .gitignore
?? Makefile
?? README.md
?? configs/
?? docs/
?? notes/
?? pyproject.toml
?? scripts/
?? src/
?? tests/
```

**未解决问题 / 环境坑**

1. `uv pip install -e .` 在当前机器上失败：`error: [Errno 17] EEXIST: mkdir '.../builds-v0/.tmpXXXX/.tmp-xxxx'`（uv 0.11.23 + setuptools 84/75 均复现，改 `UV_CACHE_DIR` 也复现）。绕行方案：venv 内用 `python -m pip install -e ".[dev]"`，已写进 Makefile 的 `install` 目标并注明原因。仅影响源码构建，二进制 wheel 安装不受影响。
2. `configs/deepseek.yaml` 的模型 id 仍为 `null`，`load_settings()` 会抛 `ConfigError`——这是刻意设计（D3），S2 跑 `/models` 后回填。
3. `make phase1` 目前必然失败（`scripts/run_phase1.py` 只抛 SystemExit），S6/S7 落地后接上。

**下一步**：S2 接入探针（列模型、普通对话、thinking 开/关、thinking + tools 的 reasoning_content 回传），全程经 `LLMClient`，结果追加到本文件。


---

## S1 复审与修复（2026-11-03）

**做了什么**

- 用户确认修复全部复审发现，范围保持 S1，不运行 S2，也不调用 DeepSeek。
- 先运行原测试：27 passed；mock 复现缓存绕过为 2 次请求、缓存失败/响应解析失败时 usage 为 0 条、Settings repr 暴露假凭据、SDK 默认重试为 2。
- 先补回归用例，首轮得到 8 failed / 26 passed，确认失败与缺陷一致。原“强制绕过缓存”断言按用户明确的缓存要求改成禁止绕过；原始异常文本断言改成安全 HTTP 状态，不删除或放宽测试。
- 强制缓存优先，v2 键加入 endpoint；usage 在解析/缓存前写入，逐次失败尝试记账，原始 usage 保留；SDK 重试关闭，封装覆盖全部 5xx；错误文本不回显供应商异常，Settings 隐藏密钥。
- 增加 USD 3 串行预算检查、价格未知拒绝、输出上限及重试预留；账单未知、账本损坏或 pending 标记阻止后续付费请求；缓存命中无需价格/SDK。进一步回归覆盖累计预算、缺失 usage、残缺账本和日志写入失败。
- 密钥扫描覆盖 index blob 与工作区（含未忽略新文件、.env.example），测试使用临时 Git 仓库验证暂存秘密即使工作区已清理也会被检出。
- Python 改为 >=3.11,<3.13，Makefile 恢复 uv editable 安装，支持指定隔离环境；新增网络阻断 fixture。未引入额外依赖。

**安装验证**

- 最初使用空缓存离线安装失败，原因是没有 setuptools；随后普通沙箱联网安装遭遇 DNS 失败。经工具批准的依赖下载在全新 `.venvs/s1-verify` 环境成功，21 packages installed，未调用任何 LLM。
- 本轮没有复现旧日志里的 EEXIST，历史记录保留，但 Makefile 不再固定绕行 pip。

```text
$ uv pip install --python .venvs/s1-verify/bin/python --cache-dir /private/tmp/trajjudge-uv-cache -e '.[dev]'
Built trajjudge; Installed 21 packages

$ UV_OFFLINE=1 make install VENV=.venvs/s1-make-verify UV_CACHE_DIR=/private/tmp/trajjudge-uv-cache
Creating virtual environment at: .venvs/s1-make-verify
Built trajjudge; Installed 21 packages

$ make test
44 passed

$ make test VENV=.venvs/s1-make-verify
# 最终提交前再次运行，结果见下方补充。
```

**未解决问题 / 边界**

- S2–S7 尚未执行：模型与价格仍为空，smoke 脚本尚未实现，phase1 仍是明确的占位入口；不把这些后续关卡误报为本关成果。
- 预算采用保守估算而非供应商账单保证，暂不支持多个进程共用账本；异常尝试可能产生未知账单，需要核实后恢复。完整磁盘故障不能承诺完整 usage，pending 护栏可防止静默继续。
- 上游的 LLM 调用如何接入统一封装，仍在对应关卡实现和验证；当前无真实模型兼容性/效果证据。本轮 LLM 请求数 0，LLM 成本 USD 0。
- 保留原有授权：用户提供的历史对话已确认虚拟环境布局及 D6 的方案 A，无需重新拍板；后续发现变化再按关卡处理。


**最终验证补充**

```text
$ make test VENV=.venvs/s1-make-verify
44 passed in 0.49s

$ git diff --check
# 无输出，exit 0。
```

提交前暂存所有本关文件后运行 `make secrets`，其 4 项测试同时覆盖实际仓库 index/工作区、.env 忽略和两个临时仓库回归场景；通过后才提交。关卡结束等待用户“继续”。


### S1 提交收尾（2026-11-04）

恢复工作时确认修复仍在暂存区，尚未创建提交。重新执行：

```text
$ make test
44 passed in 0.52s

$ git diff --cached --check
# 无输出，exit 0。
```

本次将全部 S1 修复作为单独的 fix(s1) 提交。提交前再次执行 make secrets 检查暂存区与工作区；本关结束后按用户要求停关，S2 尚未开始。没有 DeepSeek 请求，LLM 成本 USD 0。


### S2 探针结果（2026-11-04T07:59:15+00:00）

命令：`python scripts/smoke_llm.py --model deepseek-flash`

模型列表：`deepseek-flash, deepseek-v4-pro`；离线回放：False。

```json
{
  "timestamp": "2026-11-04T07:59:15+00:00",
  "models": [
    "deepseek-flash",
    "deepseek-v4-pro"
  ],
  "estimate": {
    "model": "deepseek-flash",
    "completion_calls": 5,
    "input_tokens_estimate": 5000,
    "output_tokens_cap": 4224,
    "cost_usd_estimate": 0.006569,
    "attempt_limit": 3,
    "batch_reserve_usd": 0.05,
    "pricing_basis": "peak input cache-miss and peak output; conservative estimate, not invoice"
  },
  "offline": false,
  "results": [
    {
      "probe": "plain",
      "model": "deepseek-flash",
      "thinking": false,
      "prompt_tokens": 13,
      "completion_tokens": 5,
      "returned_reasoning": false,
      "cached": false,
      "tool_calls": 0,
      "answer": "S2_READY"
    },
    {
      "probe": "thinking_off",
      "model": "deepseek-flash",
      "thinking": false,
      "prompt_tokens": 18,
      "completion_tokens": 1,
      "returned_reasoning": false,
      "cached": false,
      "tool_calls": 0,
      "answer": "5"
    },
    {
      "probe": "thinking_on",
      "model": "deepseek-flash",
      "thinking": true,
      "prompt_tokens": 44,
      "completion_tokens": 15,
      "returned_reasoning": true,
      "cached": false,
      "tool_calls": 0,
      "answer": "5"
    },
    {
      "probe": "tool_request",
      "model": "deepseek-flash",
      "thinking": true,
      "prompt_tokens": 313,
      "completion_tokens": 40,
      "returned_reasoning": true,
      "cached": false,
      "tool_calls": 1,
      "answer": ""
    },
    {
      "probe": "tool_followup",
      "model": "deepseek-flash",
      "thinking": true,
      "prompt_tokens": 105,
      "completion_tokens": 8,
      "returned_reasoning": false,
      "cached": false,
      "tool_calls": 0,
      "answer": "S2_TOOL_OK_731",
      "reasoning_replayed_verbatim": true
    }
  ],
  "cumulative_usage": {
    "calls": 7,
    "cached_calls": 1,
    "prompt_tokens": 493,
    "completion_tokens": 69,
    "cost_usd": 0.000231,
    "unpriced_models": []
  }
}
```


### S2 探针结果（2026-11-04T08:00:08+00:00）

命令：`python scripts/smoke_llm.py --offline`

模型列表：`deepseek-flash, deepseek-v4-pro`；离线回放：True。

```json
{
  "timestamp": "2026-11-04T08:00:08+00:00",
  "models": [
    "deepseek-flash",
    "deepseek-v4-pro"
  ],
  "estimate": {
    "model": "deepseek-flash",
    "completion_calls": 5,
    "input_tokens_estimate": 5000,
    "output_tokens_cap": 4224,
    "cost_usd_estimate": 0.006569,
    "attempt_limit": 3,
    "batch_reserve_usd": 0.05,
    "pricing_basis": "peak input cache-miss and peak output; conservative estimate, not invoice"
  },
  "offline": true,
  "results": [
    {
      "probe": "plain",
      "model": "deepseek-flash",
      "thinking": false,
      "prompt_tokens": 13,
      "completion_tokens": 5,
      "returned_reasoning": false,
      "cached": true,
      "tool_calls": 0,
      "answer": "S2_READY"
    },
    {
      "probe": "thinking_off",
      "model": "deepseek-flash",
      "thinking": false,
      "prompt_tokens": 18,
      "completion_tokens": 1,
      "returned_reasoning": false,
      "cached": true,
      "tool_calls": 0,
      "answer": "5"
    },
    {
      "probe": "thinking_on",
      "model": "deepseek-flash",
      "thinking": true,
      "prompt_tokens": 44,
      "completion_tokens": 15,
      "returned_reasoning": true,
      "cached": true,
      "tool_calls": 0,
      "answer": "5"
    },
    {
      "probe": "tool_request",
      "model": "deepseek-flash",
      "thinking": true,
      "prompt_tokens": 313,
      "completion_tokens": 40,
      "returned_reasoning": true,
      "cached": true,
      "tool_calls": 1,
      "answer": ""
    },
    {
      "probe": "tool_followup",
      "model": "deepseek-flash",
      "thinking": true,
      "prompt_tokens": 105,
      "completion_tokens": 8,
      "returned_reasoning": false,
      "cached": true,
      "tool_calls": 0,
      "answer": "S2_TOOL_OK_731",
      "reasoning_replayed_verbatim": true
    }
  ],
  "cumulative_usage": {
    "calls": 13,
    "cached_calls": 7,
    "prompt_tokens": 493,
    "completion_tokens": 69,
    "cost_usd": 0.000231,
    "unpriced_models": []
  }
}
```


---

## S2 接入探针完成（2026-11-04）

**做了什么**

- 用户指定 deepseek-flash，密钥从既有 .env 读取，不打印、不写入受跟踪文件；本轮不运行 S3。
- 先只读检查当前封装并查阅 DeepSeek 官方模型列表、thinking/tool-call 和价格文档。首次只读客户端调用实际列出 deepseek-flash、deepseek-v4-pro；之后正式入口的模型发现、缓存读取和错误重试均在共享 usage 中记录（endpoint=models，无生成 token）。
- 批量调用前已向用户报告：5 次 completion，约 5,000 输入、最多 4,224 输出 tokens；按高峰/cache-miss 估算 $0.006569，包含重试和额外上下文的批次预留 $0.05，计入总预算 $3。
- 新增 scripts/smoke_llm.py 和 trajjudge.smoke，支持 --list-models、--estimate、--model、--offline；普通对话、thinking off/on、工具请求/结果续答全部通过共享 LLMClient。工具仅为确定性本地 fixture，不调用其他服务。每个探针检查固定答案，工具请求检查一次调用/参数，reasoning_content 原样回传；不放宽断言或删除测试。
- thinking 显式 enabled/disabled；开启时 low effort，以减少探针成本。工具续答保持 tools 并设置 tool_choice=none，限制为单轮工具往返。配置两角色均为已验证且用户选择的 deepseek-flash，新增官方价格来源/核实日期与高峰/低峰数据，不新增依赖。
- 新增 5 个探针测试时先得到 5 failed，随后全部通过；并增加无密钥离线配置回归。原 thinking-on 测试由“省略默认参数”改为断言显式 enabled，其他覆盖保留。离线测试统一阻止网络连接。

**真实调用结果**

| 探针 | thinking 请求 | 输入 tokens | 输出 tokens | 返回 reasoning_content | tool_calls |
|---|---|---:|---:|---|---:|
| 普通对话 | off | 13 | 5 | 否 | 0 |
| thinking off | off | 18 | 1 | 否 | 0 |
| thinking on | on / low | 44 | 15 | 是 | 0 |
| 工具请求 | on / low | 313 | 40 | 是 | 1 |
| 工具续答 | on / low | 105 | 8 | 否 | 0 |

总计 493 输入 + 69 输出 = 562 tokens；按配置高峰价格保守估算 $0.000231（未四舍五入为 $0.0002307），不是供应商精确账单。5 次 completion 均无重试、无 400；预期回答分别为 S2_READY、5、5、工具调用、S2_TOOL_OK_731。续答未返回 reasoning_content 是观察结果，不隐藏，也不等同于已确认供应商实际关闭 thinking。

**证据（关键命令与输出）**

```text
$ python scripts/smoke_llm.py --model deepseek-flash --estimate
models: [deepseek-flash, deepseek-v4-pro]
completion_calls: 5, input_tokens_estimate: 5000, output_tokens_cap: 4224
cost_usd_estimate: 0.006569, batch_reserve_usd: 0.05

$ python scripts/smoke_llm.py --model deepseek-flash
# 5 个探针通过，reasoning_replayed_verbatim: true。
prompt_tokens: 493, completion_tokens: 69, cost_usd: 0.000231

$ make smoke SMOKE_ARGS=--offline
# 模型列表和全部 5 个 completion 均 cached:true。
# 客户端禁止 SDK 请求；没有新增模型请求或 token 消费。
prompt_tokens: 493, completion_tokens: 69, cost_usd: 0.000231
```

在线摘要保存 outputs/smoke/s2.json；离线摘要保存 outputs/smoke/s2-offline.json；原始 reasoning 和响应在 .cache/llm，完整 usage 在 outputs/usage/usage.jsonl，均为本地忽略文件。上方自动追加的两份摘要保留实际时间戳和逐条结果，可供核查。

**未解决问题 / 边界**

- 本关仅证明 DeepSeek 直接接口和本项目封装的接通；不证明 OpenJudge/Claw-Eval 已兼容，也不证明评分质量、稳定性或抗注入能力。
- 未发送故意省略 reasoning_content 的真实负向请求，因此没有“缺失时必然 400”的本次实验结论；该规则来自官方文档。正确回传的请求已实际成功。
- 费用使用高峰/cache-miss 保守价格，实际供应商缓存命中与低峰可能更便宜。当前累计模型消费仍为 562 tokens，缓存回放不增加。
- 本地缓存不入 Git，其他克隆需先运行探针或获得缓存，才能离线回放。S3 的 editable OpenJudge 冒烟、额外参数验证尚待下一关。

**下一步**：提交 S2 后停关，等待用户“继续”。


**S2 最终离线验证**

```text
$ make test
50 passed in 0.49s

$ git diff --check
# 无输出，exit 0。
```

提交前先暂存本关文件，再执行 make secrets（4 个检查场景），通过后创建 feat(s2) 提交。未新增任何依赖，未修改上游。


### S3 天气冒烟（2026-11-04T09:23:11+00:00）

命令：`python scripts/smoke_openjudge.py `

```json
{
  "trace_id": "openjudge-docs-weather",
  "grader": "trajectory_accuracy",
  "score": 3.0,
  "reason": "The trajectory is logically coherent, efficient, and directly fulfills the user's request by calling the weather tool and reporting the result. No unnecessary steps.",
  "metadata": {
    "raw_score": 3.0
  },
  "judge_model": "deepseek-flash",
  "thinking": false,
  "returned_reasoning": false,
  "openjudge_commit": "7d27246484e91c6ed4a349b6ebe7bd4629d9378f",
  "timestamp": "2026-11-04T09:23:11+00:00",
  "cached": false,
  "response_format_policy": "json_object with local validation against the upstream callback schema",
  "wire_observations": [
    {
      "thinking": {
        "type": "disabled"
      },
      "response_format": {
        "type": "json_object"
      },
      "request_fields": [
        "max_tokens",
        "messages",
        "model",
        "response_format",
        "stream",
        "thinking"
      ]
    }
  ],
  "usage": {
    "prompt_tokens": 504,
    "completion_tokens": 38,
    "raw_usage": {
      "completion_tokens": 38,
      "prompt_tokens": 504,
      "total_tokens": 542,
      "completion_tokens_details": null,
      "prompt_tokens_details": {
        "audio_tokens": null,
        "cache_write_tokens": null,
        "cached_tokens": 0,
        "image_tokens": null,
        "text_tokens": null
      },
      "prompt_cache_hit_tokens": 0,
      "prompt_cache_miss_tokens": 504
    }
  },
  "sample_source": {
    "source": "OpenJudge/docs/built_in_graders/agent_graders.md",
    "section": "TrajectoryAccuracyGrader",
    "openjudge_commit": "7d27246484e91c6ed4a349b6ebe7bd4629d9378f"
  },
  "estimate": {
    "completion_calls": 1,
    "input_tokens_estimate": 1200,
    "output_tokens_cap": 768,
    "cost_usd_estimate": 0.001282,
    "reserve_usd": 0.02,
    "pricing_basis": "peak/cache-miss conservative estimate"
  },
  "cumulative_usage": {
    "calls": 16,
    "cached_calls": 9,
    "prompt_tokens": 997,
    "completion_tokens": 107,
    "cost_usd": 0.000427,
    "unpriced_models": []
  }
}
```


### S3 天气冒烟（2026-11-04T09:24:23+00:00）

命令：`python scripts/smoke_openjudge.py --offline`

```json
{
  "trace_id": "openjudge-docs-weather",
  "grader": "trajectory_accuracy",
  "score": 3.0,
  "reason": "The trajectory is logically coherent, efficient, and directly fulfills the user's request by calling the weather tool and reporting the result. No unnecessary steps.",
  "metadata": {
    "raw_score": 3.0
  },
  "judge_model": "deepseek-flash",
  "thinking": false,
  "returned_reasoning": false,
  "openjudge_commit": "7d27246484e91c6ed4a349b6ebe7bd4629d9378f",
  "timestamp": "2026-11-04T09:24:23+00:00",
  "cached": true,
  "response_format_policy": "json_object with local validation against the upstream callback schema",
  "wire_observations": [
    {
      "thinking": {
        "type": "disabled"
      },
      "response_format": {
        "type": "json_object"
      },
      "request_fields": [
        "max_tokens",
        "messages",
        "model",
        "response_format",
        "stream",
        "thinking"
      ]
    }
  ],
  "usage": {
    "prompt_tokens": 504,
    "completion_tokens": 38,
    "raw_usage": {
      "completion_tokens": 38,
      "completion_tokens_details": null,
      "prompt_cache_hit_tokens": 0,
      "prompt_cache_miss_tokens": 504,
      "prompt_tokens": 504,
      "prompt_tokens_details": {
        "audio_tokens": null,
        "cache_write_tokens": null,
        "cached_tokens": 0,
        "image_tokens": null,
        "text_tokens": null
      },
      "total_tokens": 542
    }
  },
  "sample_source": {
    "source": "OpenJudge/docs/built_in_graders/agent_graders.md",
    "section": "TrajectoryAccuracyGrader",
    "openjudge_commit": "7d27246484e91c6ed4a349b6ebe7bd4629d9378f"
  },
  "estimate": {
    "completion_calls": 1,
    "input_tokens_estimate": 1200,
    "output_tokens_cap": 768,
    "cost_usd_estimate": 0.001282,
    "reserve_usd": 0.02,
    "pricing_basis": "peak/cache-miss conservative estimate"
  },
  "cumulative_usage": {
    "calls": 18,
    "cached_calls": 11,
    "prompt_tokens": 997,
    "completion_tokens": 107,
    "cost_usd": 0.000427,
    "unpriced_models": []
  }
}
```


---

## S3 OpenJudge 冒烟完成（2026-11-04）

**做了什么**

- 先读 OpenJudge README/pyproject、OpenAIChatModel/BaseChatModel、LLMGrader、TrajectoryAccuracyGrader、schema 和天气官方样例；本关只做 Accuracy 冒烟，不实现 S6 的四 grader runner。
- 上游提交：7d27246484e91c6ed4a349b6ebe7bd4629d9378f，开始时 git status --short 为空。
- 确认 api_key/base_url 或 OPENAI_* 环境变量均可设置；本项目显式传设置。extra_body 进入 self.kwargs 再传 SDK，本轮实际观察到 thinking.type=disabled。
- 发现 LLMGrader 默认 JSON Schema 与 DeepSeek 官方 JSON object 接口的差异；本地子类只做响应格式适配和原 callback schema 校验，native model/SDK/grader 仍实际执行，底层请求统一走 LLMClient。完整供应商响应加入忽略缓存，response_format 加入缓存键，未知参数/streaming 明确拒绝。
- 以 editable 方式直接安装 ../OpenJudge，没有复制替代来源、没有修改上游。OpenJudge 的运行依赖装到现有 judge 环境；未装 dev/训练 extras、未混入 Claw-Eval。新增本地安装 helper 与 Makefile install-openjudge/smoke-openjudge 入口，无新增本项目直接依赖。
- samples/weather.json 通过 AST 从官方 TrajectoryAccuracyGrader 文档示例提取，messages 逐字段相同，记录来源与提交哈希；samples/weather-score.json 保存真实结果。没有生成或代替人工标签。
- 模型调用前已告知：1 次 completion，估计输入 1200、输出上限 768 tokens，保守费用 $0.001282，本关预留 $0.02。

**安装与诊断证据**

首次对整组依赖使用相同 setuptools build_base，jieba/rouge-score 并行构建目录冲突，jieba wheel 构建失败。停止后核对 676 个上游文件，变化 0；改为先正常安装运行依赖，再只对 OpenJudge editable 构建做重定向，安装成功。

```text
$ make install-openjudge
Checked 21 packages
py-openjudge==0.2.0 (from file:///Users/x/agent-eval/OpenJudge)
Upstream file delta: 0 (676 files verified)

$ python ...  # PYTHONDONTWRITEBYTECODE=1，读取安装 metadata 与导入位置
Imported source: /Users/x/agent-eval/OpenJudge/openjudge/__init__.py
Editable metadata: {"url":"file:///Users/x/agent-eval/OpenJudge","dir_info":{"editable":true}}
```

**真实调用证据**

```text
$ make smoke-openjudge OPENJUDGE_ARGS=--estimate
completion_calls: 1, input_tokens_estimate: 1200, output_tokens_cap: 768
cost_usd_estimate: 0.001282, reserve_usd: 0.02

$ make smoke-openjudge
score: 3.0
grade reason: The trajectory is logically coherent, efficient, and directly fulfills the user's request by calling the weather tool and reporting the result. No unnecessary steps.
thinking: false, returned_reasoning: false, cached: false
wire thinking: {"type":"disabled"}
wire response_format: {"type":"json_object"}
usage: 504 input + 38 output = 542 tokens
```

本关一次付费请求、无重试，按配置高峰价保守费用 $0.0001968；S2+S3 累计 997 输入、107 输出，1104 tokens，保守费用精确计算 $0.0004275（最终摘要向上保留六位小数为 $0.000428；自动追加的早期摘要保留当时浮点舍入值）。价格为估算而非精确账单。

**验证与未解决问题**

- 四个 mock 集成用例先失败（bridge/response_format 尚未实现），实现后通过：真实 OpenJudge/native SDK 调用链、缓存回放、缺失 score 返回 GraderError、未知参数不发请求。另有 AST 官方样例一致性检查。
- 本关 extra_body 关闭 thinking 已实测成功，不需要备选方案。原生 grader 对异常 score 的限幅仍是上游行为，本关只验证合法天气样例，完整供应商响应保留供审计，不据此宣称 grader 可靠。
- 上游仍为只读依赖；后续若变更上游提交或模板，旧缓存未必命中。直接运行 judge 命令时须设置 PYTHONDONTWRITEBYTECODE=1，Makefile 已统一设置。
- S4 只读 Claw-Eval 侦察尚未执行，S5/S6/S7 不提前开展。

**下一步**：完成本关离线回放、测试与提交，停关等待用户“继续”。


### S3 天气冒烟（2026-11-04T09:27:30+00:00）

命令：`python scripts/smoke_openjudge.py --offline`

```json
{
  "trace_id": "openjudge-docs-weather",
  "grader": "trajectory_accuracy",
  "score": 3.0,
  "reason": "The trajectory is logically coherent, efficient, and directly fulfills the user's request by calling the weather tool and reporting the result. No unnecessary steps.",
  "metadata": {
    "raw_score": 3.0
  },
  "judge_model": "deepseek-flash",
  "thinking": false,
  "returned_reasoning": false,
  "openjudge_commit": "7d27246484e91c6ed4a349b6ebe7bd4629d9378f",
  "timestamp": "2026-11-04T09:27:30+00:00",
  "cached": true,
  "response_format_policy": "json_object with local validation against the upstream callback schema",
  "wire_observations": [
    {
      "thinking": {
        "type": "disabled"
      },
      "response_format": {
        "type": "json_object"
      },
      "request_fields": [
        "max_tokens",
        "messages",
        "model",
        "response_format",
        "stream",
        "thinking"
      ]
    }
  ],
  "usage": {
    "prompt_tokens": 504,
    "completion_tokens": 38,
    "raw_usage": {
      "completion_tokens": 38,
      "completion_tokens_details": null,
      "prompt_cache_hit_tokens": 0,
      "prompt_cache_miss_tokens": 504,
      "prompt_tokens": 504,
      "prompt_tokens_details": {
        "audio_tokens": null,
        "cache_write_tokens": null,
        "cached_tokens": 0,
        "image_tokens": null,
        "text_tokens": null
      },
      "total_tokens": 542
    }
  },
  "sample_source": {
    "source": "OpenJudge/docs/built_in_graders/agent_graders.md",
    "section": "TrajectoryAccuracyGrader",
    "openjudge_commit": "7d27246484e91c6ed4a349b6ebe7bd4629d9378f"
  },
  "estimate": {
    "completion_calls": 1,
    "input_tokens_estimate": 1200,
    "output_tokens_cap": 768,
    "cost_usd_estimate": 0.001282,
    "reserve_usd": 0.02,
    "pricing_basis": "peak/cache-miss conservative estimate"
  },
  "cumulative_usage": {
    "calls": 20,
    "cached_calls": 13,
    "prompt_tokens": 997,
    "completion_tokens": 107,
    "cost_usd": 0.000428,
    "unpriced_models": []
  }
}
```


**S3 最终验证**

```text
$ make test
56 passed in 2.89s

$ make smoke-openjudge OPENJUDGE_ARGS=--offline
score: 3.0, cached: true
cumulative prompt_tokens: 997, completion_tokens: 107, cost_usd: 0.000428

$ uv pip check --python .venvs/judge/bin/python
Checked 98 packages; All installed packages are compatible

$ python ...  # 对照初始上游 SHA-256 manifest
Final upstream file delta: 0

$ git -C ../OpenJudge status --short
# 空；上游工作区干净。

$ git diff --check
# 无输出，exit 0。
```

额外费用回归复现多条记录浮点累加向下舍入；修复为 Decimal 精确累加后摘要向上保留六位，最终累计 $0.000428。原始 token 与早期日志保留，未新增真实请求。提交前暂存本关文件并运行 make secrets，通过后创建 feat(s3) 提交。
