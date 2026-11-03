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
