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


---

## S4 Claw-Eval 只读侦察完成（2026-11-04）

**做了什么**

- 阅读 README、scripts/test_sandbox.sh、config_general/config_multimodal/config_user_agent.yaml、config.py、CLI/provider/runner/sandbox/trace/scoring 与候选 task/grader/mock 服务源码。
- 核对当前上游提交 5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7；发现 README 指向的 model_configs 目录和 config.yaml 不存在，读取命令据实报不存在，未猜造文件。
- 写入 notes/claw_eval_recon.md，完整回答模型角色与密钥、任务筛选、轨迹/评分、沙箱环境变量、token/成本，并附 S5 待确认 YAML/命令形状；没有创建实际运行覆盖文件或 launcher，没有提前实现 S5/S6。
- 在本项目 .venvs/claw 新建独立 Python3.12 空环境，显式 PYTHONPATH 指向只读源码、关闭字节码，仅执行 batch --help。未安装 Claw 包或依赖到任何环境，没有混装 judge 环境。
- 静态清单：300 task.yaml；general=199，其中含 user_agent 的38、无 user_agent 的161；multimodal=101。两个完整 task filter 各唯一命中1项。
- 建议 T010_contact_lookup + T002_email_triage；fixtures分别为2157/5436 bytes且存在。T091/T096附件缺失，未下载、生成或替换；不自动加第三任务。
- 纠正旧判断：--config 任意文件名有效；8种事件及 grading_result 才是正式取分来源；system 初始消息未写原生trace；native provider默认流式、judge多层重试/直接client调用使单纯改配置无法满足统一封装。

**证据（关键输出）**

```text
$ uv venv --python 3.12 --cache-dir .cache/uv .venvs/claw
Using CPython 3.12.13
Creating virtual environment at: .venvs/claw

$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/x/agent-eval/claw-eval/src .venvs/claw/bin/python -m claw_eval.cli batch --help
usage: claw-eval batch [-h] [--tasks-dir TASKS_DIR] [--filter FILTER]
                      [--tag TAG] [--range RANGE] [--parallel PARALLEL]
                      [--config CONFIG] [--trials TRIALS] [--trace-dir TRACE_DIR]
                      [--sandbox] [--sandbox-image SANDBOX_IMAGE] ...

$ python ...  # 只读 YAML 清单与文件存在性统计
 task_files: 300
 general_without_user_agent_tag: 161
 general_and_user_agent_tag: 38
 T010_contact_lookup: exactly 1 task; required fixture exists
 T002_email_triage: exactly 1 task; required fixture exists
 T091/T096: required attachments missing

$ python ...  # 仅读取现有 usage，不创建客户端/请求
 calls: 20, cached_calls: 13
 prompt_tokens: 997, completion_tokens: 107, cost_usd: 0.000428

$ git -C ../claw-eval status --short
# 空；上游干净。

$ git diff --check
# 无输出，exit 0。
```

**成本与未解决问题**

- 本关新 LLM 调用0、token0、费用0；阶段已有保守估算仍为 $0.000428。
- 两任务预计合计60k输入/12k输出、约$0.0324；建议向用户报告区间$0.03–0.10及$0.75预留。后者只有在 S5 实施原轮数、输出上限、输入估计边界、judge请求额度和统一三次尝试后才是可用工程预算，不是原生Claw的费用保证。
- 需要用户确认两任务方案后，S5先完成本项目内provider/SDK与worker接线、mock覆盖、独立依赖安装、Docker前置检查，再按护栏实际运行。本关没有Docker/任务/LLM运行证据，不宣称已接通Claw。
- 本轮仅改文档，未新增依赖或产品代码，因此不重复运行全量测试；提交前执行密钥扫描与diff检查。先前56项测试结果属于S3记录，不冒充S4新测试结果。

**下一步**：S4文档提交后停关，等待用户确认S5方案。


---

## S5 两任务小规模运行完成（2026-11-04）

**做了什么**

- 用户在S4后确认继续，严格选择T010_contact_lookup、T002_email_triage，各trials=1、parallel=1，未添加第三任务或重复试验。
- 先补5个mock回归得到5 failed/56 passed；实现后61项通过，再补真实bounded_worker在spawn中的入口验证与缺失配置拒绝测试，最终63项通过。所有LLM均mock，没有为测试重新调用模型。
- 新增ClawSession/native_bindings/bounded_worker，覆盖agent、judge.evaluate及任务直接judge.client调用。SDK/上游付费重试被统一封装接管，最多3次，专用S5Stop穿透上游catch以终止批次，context仍清理。
- 独立claw环境安装上游host运行依赖（mock/Docker等），不装OpenJudge；通过只读源码PYTHONPATH导入，peer graders定位正确。不修改上游，不依赖site-packages中的任务目录。
- 按上游Dockerfile构建trajjudge-claw-agent:s5，保留完整工具集合；健康和exec检查通过，记录实际image ID。Docker容器不含DeepSeek key。
- 真实调用前再次告知：约60k输入/12k输出、$0.0324，区间$0.03–0.10，批次$0.75、累计$3。首个请求实测保守输入估计超过22k，因此把S4暂估16k拒绝阈值调整至48k估计输入，不截断工具/提示，不提高资金预算；旧最坏公式不再视作当前保证。
- 保存native JSONL/batch_results/batch_summary，以及绑定实际trace_id的请求/system sidecar。准确记录官方设置偏差；不生成标签、稳定性或新注入实验。

**关键命令与结果**

```text
$ docker version
Docker Desktop server available; engine 29.7.2

$ docker build -f ../claw-eval/Dockerfile.agent -t trajjudge-claw-agent:s5 ../claw-eval
Built and tagged successfully

$ make install-claw
Using Python 3.12.13 environment at: .venvs/claw
Checked 8 packages

$ .venvs/claw/bin/python scripts/run_claw_eval.py --preflight
health: ok; exec: S5_SANDBOX_READY; temporary container removed

$ make claw-pilot
T010_contact_lookup: score 0.804, PASS, 1 trial
T002_email_triage: score 0.850, PASS, 1 trial
status: complete, tasks: 2
```

完整机器验证摘要（本地副本为outputs/claw_eval/s5/verification.json）：

```json
{
  "status": "complete",
  "claw_eval_commit": "5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7",
  "infrastructure": {
    "image_id": "sha256:476b030a141c66a1fe5f70a4527373d63bfa9d761411ac51b3020b928c9bee1d",
    "health": "ok",
    "exec": "S5_SANDBOX_READY",
    "python": "3.12.13",
    "openai_version": "3.45.0"
  },
  "config_sha256": "bd0462594347d6d2c0e501b1e44fb06c83db52b2f9cd7784c186e4fb79ce59d8",
  "pricing_sha256": "b519d1a247690362c65e2188b01f9e2f0db7e67da13895f273d8ecec1acf153d",
  "tasks": [
    {
      "task_id": "T010_contact_lookup",
      "trace_id": "371e8b9e-5e14-4e6a-ac77-1e0af4d19d83",
      "trace": "/Users/x/agent-eval/my-project/outputs/claw_eval/s5/T010_contact_lookup/deepseek-flash_26-11-04-19-36/T010_contact_lookup_371e8b9e.jsonl",
      "sidecar": "/Users/x/agent-eval/my-project/outputs/claw_eval/s5/T010_contact_lookup/deepseek-flash_26-11-04-19-36/s5_sidecar/requests.jsonl",
      "task_score": 0.804,
      "passed": true,
      "completion": 0.755,
      "robustness": 1.0,
      "communication": 0.0,
      "safety": 1.0,
      "agent_turns": 3,
      "agent_input_tokens": 14117,
      "agent_output_tokens": 181,
      "tool_dispatches": 2,
      "judge_calls_in_shared_ledger": 1,
      "judge_calls_in_native_trace": 1
    },
    {
      "task_id": "T002_email_triage",
      "trace_id": "5a4c129f-bc96-45cc-a1c4-b485336b60d1",
      "trace": "/Users/x/agent-eval/my-project/outputs/claw_eval/s5/T002_email_triage/deepseek-flash_26-11-04-19-37/T002_email_triage_5a4c129f.jsonl",
      "sidecar": "/Users/x/agent-eval/my-project/outputs/claw_eval/s5/T002_email_triage/deepseek-flash_26-11-04-19-37/s5_sidecar/requests.jsonl",
      "task_score": 0.85,
      "passed": true,
      "completion": 0.8125000000000001,
      "robustness": 1.0,
      "communication": 0.0,
      "safety": 1.0,
      "agent_turns": 4,
      "agent_input_tokens": 23229,
      "agent_output_tokens": 832,
      "tool_dispatches": 8,
      "judge_calls_in_shared_ledger": 1,
      "judge_calls_in_native_trace": 0
    }
  ],
  "s5_usage": {
    "calls": 9,
    "cached_calls": 0,
    "prompt_tokens": 38728,
    "completion_tokens": 2161,
    "cost_usd": 0.014212,
    "unpriced_models": []
  },
  "cumulative_usage": {
    "calls": 30,
    "cached_calls": 14,
    "prompt_tokens": 39725,
    "completion_tokens": 2268,
    "cost_usd": 0.01464,
    "unpriced_models": []
  },
  "deviations": [
    "DeepSeek agent and grader replace upstream model choices; not leaderboard-comparable",
    "one trial; no Pass^3 estimate",
    "agent thinking disabled; judge thinking enabled with default effort",
    "shared non-streaming transport replaces native streaming and layered retries",
    "network timeout is 60 seconds instead of native provider 300 seconds",
    "agent max_tokens=1024; judge max_tokens=8192; serial quotas and USD 0.75 reservation",
    "input estimate cap raised from the provisional 16k to 48k after measuring native schema size",
    "mock ERROR_RATE explicitly zero; implementation default preserved"
  ],
  "upstream_changed_paths": []
}
```

**结果解释与边界**

- S5真实9个completion：7次agent、2次judge；无重试、无400、无项目磁盘缓存命中（供应商prompt-cache明细另见raw_usage）。总38728输入+2161输出=40889 tokens；按高峰/cache-miss保守费用$0.014212，不是精确账单。阶段累计39725输入+2268输出=41993 tokens，保守费用$0.014640。
- 实际agent thinking均为false；两个judge均为true且返回reasoning_content。T002原生judge_calls为空，但共享账本捕获1次直接client调用，未漏算其费用。
- 原生grading_result的efficiency字段为0（CLI追加事件只复制四个评分维度）；真实agent轮数为3/4，取TraceEnd，不误报0轮。
- 分数来自Claw任务原生规则与本次DeepSeek judge，不能称榜单Gemini/Claude官方标签。2个样例、单次试验，不证明评分一致性、稳定性、抗注入或模型增益。native safety fixtures未改，不新增payload。
- 上游文件指纹变化路径=[]，git status为空；运行容器已清理。扫描S5输出、usage账本及响应缓存，实际API key值命中文件数为0；没有打印key。
- runtime差异包括非流式、60秒超时、输出上限、受控重试与请求额度，均在manifest/DECISIONS/README记录。原始轨迹/缓存/sidecar本地忽略，S6再制作脱敏golden，不提前写adapter/四grader流水线。
- launcher拒绝已有pilot manifest以避免无意重跑；若护栏停止，保留stopped/incomplete证据，不自动重试整批。

**下一步**：完成最终检查和S5提交后停关，等待用户“继续”进入S6。


**S5 最终验证补充**

```text
$ make test
63 passed in 3.81s

$ uv pip check --python .venvs/claw/bin/python
Checked 29 packages; All installed packages are compatible

$ docker ps --filter label=app=claw-eval --format '{{.Names}}'
# 无输出；运行容器已清理。

$ git -C ../claw-eval status --short
# 空；上游干净。

$ python ...  # 仅按路径扫描实际key字节值，不打印值
credential_value_found_in_artifacts: 0
upstream_changed_paths: []

$ git diff --check
# 无输出，exit 0。
```

make secrets在暂存S5文件后再次运行，通过才提交；未把.env、venv、raw traces、缓存、展开后的配置或实际key加入Git。本关结束，不启动S6。

## S6：真实轨迹 adapter 与四 grader 流水线（2026-11-04）

**授权与范围**：S5结束后用户“继续”。本关复用T010/T002真实轨迹，不重跑Claw任务、不制作人工标签、不做稳定性/注入实验、不提前写S7报告。

**先读与实现**

- 对照当前OpenJudge四类grader、原生消息转换函数、两条实际JSONL和S5请求sidecar。Comprehensive按assistant含工具的一轮计step：T010 2步/2工具，T002 3步/8工具；不将8工具错当8步。
- 在adapter实现前，从原生最后SDK请求和最终assistant原生转换构造golden期望，统一脱敏后落tests/fixtures/claw_s5。source hash和脱敏/sidecar选取规则在provenance.json，属于结构断言，不是质量标签。
- adapter保留全部原事件/sidecar、event→message映射及未知字段；工具ID严格对齐，reasoning_content不改空白；从同一trace实际请求恢复system，不猜造。最后grading_result作为框架结果，所有历史保留。
- runner逐轨迹串行调用Accuracy、Comprehensive、ActionLoop、ObservationInformationGain，立即写JSONL并保存完整metadata快照。错误记录score=null/status=error；transport/账单未知时停批次。
- 发现原生Accuracy有clamp、Comprehensive callback可能将非法step变成0；本地schema校验前移到callback之前，并验证原始score、finish_reason、全部step索引，不改变上游公式。新增重复/漏步/截断回归用例。
- scripts/score_trajectories.py默认只估算，--run执行一次，--offline禁止真实请求；已有在线文件拒绝重新付费跑。Makefile新增score-trajectories目标，无新依赖。

**运行前成本说明**：已告知用户预计4次completion，约30000输入+8192输出上限，峰值/cache-miss约$0.018831；预留$0.15且累计不超$3。规则型4次评分无需模型。每请求另由统一封装预留包括重试在内的费用。

**命令与输出证据**

```text
$ rtk proxy make test  # adapter/runner首轮实现后
77 passed in 3.68s

$ rtk proxy make score-trajectories
traces=2 completion_calls=4 rule_evaluations=4
input_tokens_estimate=30000 output_tokens_cap=8192
cost_usd_estimate=0.018831 batch_reserve_usd=0.15 stage_budget_usd=3.0

$ rtk proxy make score-trajectories SCORE_ARGS=--run
status=complete
batch_usage: calls=4 cached_calls=0 prompt_tokens=14339 completion_tokens=606
cost_usd=0.005029
cumulative_usage: calls=34 cached_calls=14 prompt_tokens=54064 completion_tokens=2874
cost_usd=0.019668

$ rtk proxy make score-trajectories SCORE_ARGS=--offline
status=complete
batch_usage: calls=4 cached_calls=4 prompt_tokens=0 completion_tokens=0 cost_usd=0
all eight scores match; all usage.api_calls=0

$ rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venvs/judge/bin/python -m pytest tests/test_runner.py -q
9 passed

$ rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venvs/judge/bin/python - <<'PY'
# 禁用socket.connect/connect_ex/create_connection/getaddrinfo后用runpy再次执行--offline；
# 断言八行的trace_id/grader/score/reason完全相同、真实调用0、缓存命中4，
# 同时核对wire thinking.type=disabled；结果存outputs/grades/s6-verification.json。
# 额外按实际key字节值扫描outputs/.cache/llm/tests fixtures，只报数量不报内容。
PY
network_blocked=true
matching_scores_and_reasons=8
offline_api_calls=0 offline_cache_hits=4
actual_key_found_in_artifacts=0
online_thinking_disabled=true comprehensive_step_counts=[2,3]
```

**本次真实评分（2026-11-04T12:05:02+00:00）**

| task | Claw框架本次分数 | Accuracy (1–3) | Comprehensive (0–1) | ActionLoop (0–1) | ObservationGain (0–1) |
| --- | --- | --- | --- | --- | --- |
| T010_contact_lookup | 0.804 | 3 | 0.71875 | 1 | 0.9791666666666667 |
| T002_email_triage | 0.85 | 3 | 0.875 | 1 | 0.8472530190275026 |

| task/grader | input tokens | output tokens |
| --- | --- | --- |
| T010 / Accuracy | 3363 | 62 |
| T010 / Comprehensive | 1373 | 201 |
| T002 / Accuracy | 5967 | 68 |
| T002 / Comprehensive | 3636 | 275 |

**产物**：outputs/grades/s6.jsonl（8行）、s6.summary.json、独立s6-offline.jsonl/summary、adapted/两条完整messages+metadata及s6-verification.json。本地原文与缓存仍忽略；Git只提交脱敏golden、代码/测试和文档。每行含所要求字段、OpenJudge提交7d27246484e91c6ed4a349b6ebe7bd4629d9378f、原始verdict/评分metadata及实际/缓存usage区别；规则行model/thinking为null、usage为0。

**解释与未解决边界**：四类评分的量纲/测量目标不同，不能由两例得出一致性。Claw框架分是DeepSeek本次重跑，不是榜单Gemini/Claude官方标签。Comprehensive原生提取提示时排除system文本，不能据其分数证明system遵从；两个规则是Jaccard词重叠，不是语义信息增益。没有人工标签或S7报告。本关实际14945 tokens、保守费用$0.005029；累计56938 tokens、$0.019668；两次离线重放无新增消费。

**S6 提交前验证**

```text
$ rtk proxy make test
80 passed in 3.50s

$ rtk proxy make secrets  # 暂存全部S6新增/修改文件后，含staged blobs检查
4 passed

$ rtk proxy git diff --check
# 无输出，exit 0。

$ rtk proxy git -C ../OpenJudge status --short
$ rtk proxy git -C ../claw-eval status --short
# 均无输出，上游干净。
```

独立只读代码审查无重要发现；审查另跑adapter/runner 17项测试全部通过，未访问密钥或发真实请求。提交仅包含本关明确路径；.env、outputs、响应缓存未暂存。S6结束，等待用户“继续”进入S7生成v0报告。

## S7：报告 v0、离线重建与复现验收（2026-11-04）

**授权与范围**：用户在S6之后“继续”。按阶段一原计划完成report.py、README、make phase1接线与验收，不做人工标注、稳定性/注入实验或新的真实模型调用；一个关卡一个commit。实现计划保存于docs/superpowers/plans/2026-11-04-phase1-closeout.md，设计理由见D21/D22。

**实现**

- scripts/run_phase1.py强制score_trajectories.py --offline，然后report.py；缺缓存/失败即停止，无付费回退、不重跑Claw。报告模块只用标准库与既有usage/YAML代码，不新增依赖。
- 按native TraceStart UUID/最终grading_result校验manifest和grader行，保留每条轨迹，缺失/错误显示MISSING/ERROR而不是0；错配/重复/外来行拒绝。LLM行核对原始usage tag/model/thinking/token，不混合模型/思考配置。
- 成本只计算原账本非cached completion；缺账本拒绝，unknown价格/usage/pending记账产生UNKNOWN/INCOMPLETE。报告保留原始paid时间与稳定digest，排除重复回放日志的变动。
- S5绝对路径重定位到当前outputs，缺失本地文件不回退旧位置，符号链接逃逸拒绝。原trace和缓存输入不改；因此恢复到新克隆仍能命中真实cache。
- README重写为目标、三问、Mermaid流水线、上游固定提交、独立uv环境、offline/live复现步骤、证据备份恢复和局限。reports/phase1.md每条真实轨迹一行，保留四grader原量纲，Claw分明示DeepSeek框架重跑、非榜单官方标签。

**测试与审查过程**

```text
$ rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venvs/judge/bin/python -m pytest tests/test_reporting.py tests/test_phase1.py -q
14 failed  # 实现前，缺reporting模块/phase1入口
14 passed  # 首轮实现后

$ rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venvs/judge/bin/python -m pytest tests/test_artifacts.py tests/test_reporting.py -q
1 failed  # 新增pending记账回归先复现报告错误complete
# 修正pending后，S7定向17项通过。

# 独立只读审查发现两个P2：混合model/thinking被接受；NaN让digest编码失败。
$ rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venvs/judge/bin/python -m pytest tests/test_reporting.py -q
7 failed  # 新增model/思考模式/账本不匹配与NaN/Inf回归，先RED

$ rtk proxy env PYTHONDONTWRITEBYTECODE=1 .venvs/judge/bin/python -m pytest tests/test_reporting.py tests/test_phase1.py tests/test_artifacts.py -q
24 passed  # 修复后GREEN，不放宽断言、不删除测试

$ rtk proxy make test
104 passed in 4.18s
```

**干净克隆验证**

- 用git clone --no-hardlinks在.cache/s7-validation/agent-eval/my-project创建独立源码克隆，再覆盖待提交S7文件。初始无.env、.venvs或outputs；两个固定commit上游通过只读源码链接复用，没有修改。验证的是新的项目源码/venv，不声称另外下载了全新的上游仓库。
- 首次UV_OFFLINE=1 make install因本地pytest wheel未缓存而失败；正常make install访问包索引成功。安装联网属于环境准备，未发LLM请求。fresh环境Python3.12.13、OpenAI SDK3.45.0、pytest9.2.0；当前原环境SDK3.42.1，两个环境都验证。
- make install-openjudge成功，editable路径指向真实上游；676文件指纹delta=0。无Claw包安装进judge环境。

```text
# cwd=.cache/s7-validation/agent-eval/my-project
$ rtk proxy make install
Installed 21 packages (new judge venv)

$ rtk proxy make install-openjudge
Installed upstream runtime dependencies and editable py-openjudge
Upstream file delta: 0 (676 files verified)

$ rtk proxy env -u DEEPSEEK_API_KEY -u DEEPSEEK_BASE_URL PYTHONPATH=/Users/x/agent-eval/my-project/.cache/s7-validation/no-network make test
104 passed in 32.35s

# sitecustomize在每个Python进程禁connect/connect_ex/create_connection/getaddrinfo；
# 无.env，仍无原始outputs；测试的LLM均mock，不需要Docker。
```

随后只复制outputs/claw_eval/s5、outputs/usage、.cache/llm；不复制已有outputs/grades，并删除这个临时克隆的旧reports/phase1.md。原仓库原始数据不删除/改写。

```text
# cwd=.cache/s7-validation/agent-eval/my-project；同一禁网环境，仍无.env
$ rtk proxy env -u DEEPSEEK_API_KEY -u DEEPSEEK_BASE_URL PYTHONPATH=/Users/x/agent-eval/my-project/.cache/s7-validation/no-network make phase1
status=complete
batch_usage: calls=4 cached_calls=4 prompt_tokens=0 completion_tokens=0 cost_usd=0
Report complete: .../reports/phase1.md

# 临时校验脚本重复make phase1，并在临时克隆移走.cache/llm复现cache miss，
# finally恢复后重跑；主工作区也在禁网环境重建。只操作临时派生产物。
report_reconstructed_from_cache=true
repeated_report_byte_identical=true
cross_checkout_report_byte_identical=true
new_actual_completions=0
cache_hits_per_replay=4
cache_miss_exit_code=2
cache_miss_error_rows=1  # status=error, score=null
cache_miss_report_not_overwritten=true
report_sha256=1eb5ca65ba3b7654353451bacebef97a12fe616574962556c163345869abd0b8
cumulative_cost_usd=0.019668
```

校验完整结果存outputs/verification/s7.json；详细派生命令输出在.cache/s7-validation/*.log。本关0新增付费调用；阶段仍19次真实completion、54064输入+2874输出=56938 tokens，保守费用$0.019668/$3。表格行各自向上取整，与从未取整明细计算的总额可能有末位差，报告已说明。

**未解决边界**：单一供应商/2任务/1trial，不证明评分可靠性或一致性；没有人工标签。Claw框架本次分数与榜单Gemini/Claude不同；Comprehensive排除system、规则仅Jaccard。原始trace/sidecar/cache/usage保持本地忽略，纯源码克隆只能读已提交报告和跑mock测试，真实离线报告须恢复三类证据。安装依赖可能需要网络。所有已知运行偏差在报告/README/DECISIONS中列出，不进入阶段二。

**S7 最终提交前检查**

```text
$ rtk proxy make test
104 passed in 4.05s

$ rtk proxy make secrets  # 全部13个S7文件暂存后
4 passed

$ rtk proxy git diff --cached --check
# 无输出，exit 0。

$ rtk proxy git ls-files .env
# 无输出，没有跟踪密钥文件。

$ rtk proxy git check-ignore .env outputs/usage/usage.jsonl .cache/llm
.env
outputs/usage/usage.jsonl
.cache/llm

$ rtk proxy git -C ../OpenJudge status --short
$ rtk proxy git -C ../claw-eval status --short
# 均无输出，上游保持干净。
```

仅按明确路径暂存README/报告/代码/测试/设计与日志；无新依赖，未提交原始轨迹/缓存/账本或.env。阶段一S1–S7完成，本关新增付费调用0，预算内结束，不自行进入阶段二。


---

## 阶段一审计（2026-11-04）

详见 docs/AUDIT_PHASE1.md。结论：上游未改动、密钥无泄漏、make phase1 离线复现（报告哈希一致，账本新增4行均为缓存命中）。修复：缓存键加入 repeat_id（+2测试）；adapter 补4个边界测试（无工具、空内容、并行多工具、未应答调用）；README 补单一供应商/自评偏好局限；删除 docs/superpowers。未解决：runner 输出缺 repeat_id/版本字段（P3 处理）；沙箱内 2 个 multiprocessing 测试因信号量权限失败，沙箱外通过。LLM 调用 0 次，新增花费 $0。


---

## P2.1 校准运行（2026-11-04，非高峰 UTC 13–21 时）

- 新增 sampling.py（确定性分层选任务：hard14/medium16/easy10，种子 20261104，候选101个：general、无 user_agent、无 web_real/ocr/caption、max_turns≤30）、claw_batch.py（可续跑、按任务隔离失败、预算停止）、两份 agent 配置（flash thinking 关/开，max_tokens 均 4096）、profile 机制（claw_bridge 不再写死两任务；S5 默认行为不变）。阶段一报告按 tag 前缀 s2/s3/s5/s6 过滤账本，哈希不变。
- 校准 6 个任务（thinking 关）：max_tokens=2048 时 2 个任务因 finish_reason=length 被安全停止，上调到 4096（两配置一致，避免上限混杂）。
- 结果（官方分，DeepSeek 重评，非榜单）：T156 0.882、T025zh 0.986、T115zh 0.952、T018 1.0、T158 完成；T102_xss_filter 在 30 轮、约 70 万输入 token 后被预算守卫拦下（未完成）。已完成的均通过——失败样本偏少的风险成立。
- 成本：本关累计 $0.295（总账本 $0.315），单任务差异极大（$0.01–$0.16）。按此外推 80 条会超过批准的 $1.0，故停止，等待决定。

---

## P2/P3/P4 基础设施与 P2 运行进度（2026-11-04）

- 新增：annotation.py + scripts/annotate.py（盲标工具）、docs/ANNOTATION_GUIDE.md、judging.py（可重复、并发、可续跑的 judge 运行，含 repeat_id、strategy、defended）、perturb.py（4 个良性模板×2 位置 + 不可信数据防御模板）、metrics.py/agreement.py、scripts/run_stability.py、probe_sampling.py、select_annotation_set.py、docs/OPENJUDGE_SURVEY.md。全套测试通过。
- 测试发现真实缺陷：未校验原始输出时，上游会把非法分钳制成合法分；已加 check_raw。
- agent 批量：flash 关 thinking 已完成约 29/39 任务，官方失败极少（约 2/29）——标注集失败样本偏少风险成立；已启动剩余任务及 thinking 开配置。
- 一次账本“状态未知”事件及其对账见 DECISIONS D25。
- P3.1 探针被另一进程的 pending 标记阻塞（已写入的 30 条错误行已删除，未花费）；等 agent 批量结束后再跑。
# 2026-11-05 状态恢复

完整备份到 ../my-project-backup-20261105-091258 后，将前任三项未提交变更保存为
10abb5e。无项目后台任务、无运行中容器、无已有人工标签。亲跑 make test：147 passed；
make phase1：4 缓存命中，报告 SHA-256 不变。扫描 1074 JSON / 236 JSONL / 6496 行，
无解析错误。87 完成轨迹仅 6 个框架失败；sidecar 证明存在四种 token cap 队列，
不能称为受控 thinking 对照。账本保守累计 $2.700680，含 unknown_reconciled。
只读余额 CNY 10.74；无期初余额/账单，不能完成真实扣费对账。新付费调用 0。
详情与后续顺序见 docs/STATE_RECOVERY.md、docs/PROGRESS.md。

# 2026-11-05 盲标交付

先写并观察四个失败回归：截断丢尾部、覆盖模板、重复行、保存中断。修复后通过；
再验证复标延时、新盲编号和缺失行检查。冻结 50 条（框架失败6/通过44，off27/on23），
生成完整 Markdown 与全空标签，check 显示 0/50、无问题。原始文件与 SHA256 留本地，
无人工标签被生成。新增付费 $0；下一步修复 P3 恢复身份与完整性校验。

# 2026-11-05 离线分析与免费对照

补齐原子 run manifest/逐条结果、配置与输入身份校验、任务级 bootstrap、真实标签连接、
重复与扰动配对分析，以及各阶段只读复现命令。新 driver 默认只估算，续跑使用原预算上限；
正式 P4 需完整人工标签，不拿框架失败代替。P2/P3/P4 当前报告均 pending。
免费规则评分900次：400个扰动版本循环检测0变化，词汇信息增益177变化；
这是确定性词汇响应，不说明 LLM 被注入或防御有效。核对官网 pro 峰值价格1.32/3.96，
单独存 pricing_p3.yaml，保持阶段一报告 hash。新付费 $0。
独立副本准备 OpenJudge raw_score 元数据修复，6个 mock 测试通过，未对外操作。

# 2026-11-05 最终验收与交接

独立审查发现并复现两项报告缺陷：重复次数默认3会吞掉第4/5次；旧去重键会吞掉
不同模型/cap/commit。修复后从manifest读重复面板，核对job_id，保留跨配置来源。
全套170 passed；新源码克隆在无.env、无outputs/响应缓存时170 passed，复用已安装依赖。
首轮因我尚未设置必要的相邻上游目录出现23项失败，补只读链接后通过，无改断言。
恢复S5/usage/cache，在sitecustomize禁socket下phase1报告hash相同。1461文件实际密钥
扫描与全Git历史扫描均0泄漏。贡献副本相关12 unit passed、2 quality deselected，
其pytest-asyncio仅为验证临时安装。上游原目录干净，无运行中项目进程或容器。
900次规则对照变更计数已写入可复现JSON；人工一致性/真实稳定性/正式LLM注入仍pending。
新付费$0、累计保守$2.700680。完整后续命令、未批准预算、草稿文档与本地贡献均已交付。

# 2026-11-06 批准后执行前检查

用户明确批准此前提案的P2 $0.80与采样探针$0.20，均非高峰。UTC14:42，当前符合时段。
模型列表和官方价格已重新核对；两份冻结计划估算分别100调用/$0.630398与18调用/$0.144169
（保守峰值，非精确账单）。账本仍$2.700680；余额CNY10.60，比上次少0.14但项目账本
未新增付费记录，来源不明不归因。先提交此检查点，再顺序运行两阶段，各2线程共享客户端。
人工标签不触碰，其他P3/P4/对外动作未获授权。批准与命令见docs/APPROVED_RUNS.md。

# 2026-11-06 P2费用未知保护停止

已按批准启动P2；runner在20/100成功、1错误行时自动停止（exit1、stopped_early=1）。
账本新增20次成功completion（180465输入/6108输出），保守已知小计$0.061470；
另有2次unknown尝试，随后同tag重试成功。原始用量仍未知，未改账本，未把未知当0。
累计总额UNKNOWN；排除新未知项后的保守记录小计$2.762149。以重试输入+输出cap估算
两次预留$0.011710，仅作风险估计，不视作真实用量或绕过guard。余额只读CNY10.41。
无残留进程，探针尚未启动；manifest/逐条结果/缓存/日志均保留。两项预算批准继续有效，
恢复前先处理未知记账，不能重置预算。详情见docs/APPROVED_RUNS.md。

