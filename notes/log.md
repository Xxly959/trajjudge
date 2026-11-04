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
