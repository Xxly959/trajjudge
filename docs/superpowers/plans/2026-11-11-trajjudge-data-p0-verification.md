# TrajJudge P0 验收记录

2026-11-11，本地离线执行。范围为冻结证据校验、导出快照和质检；没有调用模型、改动人工标注或发布数据。工作区已有的 v1 导出器和测试作为修复基线。

## 最小复现

在项目根目录运行。示例只写入临时目录，使用合成标签和轨迹。

```sh
demo_parent=$(mktemp -d)
demo_root="$demo_parent/example"
.venvs/judge/bin/python samples/dataset_demo.py "$demo_root"
cat "$demo_root/outputs/dataset/CURRENT"
rm "$demo_root/outputs/traces/a.sidecar.jsonl"
.venvs/judge/bin/python scripts/build_dataset.py --root "$demo_root"
.venvs/judge/bin/python scripts/build_dataset.py --root "$demo_root" --check
```

创建示例退出 0，发布 3 条轨迹、2 个任务，排除 1 次。删除 sidecar 后，同一合成输入上的 v1 导出仍退出 0，并覆盖为 2 条轨迹；v2 退出 1，指出配置、任务及冻结轨迹 ID。此时 `CURRENT` 和原快照的三个文件都保持原样，`--check` 仍退出 0。本地保留 v1 代码和复跑记录于 `.cache/trajjudge-data-p0/`。

## 验收项

| 验收项 | 证据 | 状态 |
| --- | --- | --- |
| 复现静默缩水；修复后冻结证据错误保留有效输出 | `.venvs/judge/bin/python -m pytest tests/test_dataset.py -o addopts='' -q` 退出 0，13 项通过。覆盖轨迹或 sidecar 缺失、JSONL 损坏、哈希变化、ID 被移除或被后续记录取代、最新运行中 ID 重复、冻结记录重复、盲标键重复和冻结配置错配。普通非冻结坏运行仍按原因排除。 | 通过 |
| 发布中断与报告错配可检测 | 自动测试在切换 `CURRENT` 前注入失败，旧快照仍可校验。独立验收另外在快照落盘后、指针切换前模拟进程退出 93，旧快照可读；替换报告后，`--check` 退出 1。没有测试突然断电。 | 通过 |
| 数据和报告可溯源、可重建 | `make dataset` 两次均退出 0；`CURRENT` 与三个文件逐字节相同。行结构版本为 1，快照版本为 2。对照了 181 个输入文件的 SHA-256，真实 JSONL 与 v1 字节相同，v1 两个旧文件保持原样。 | 通过 |
| 核对真实分母和质检 | 从 JSONL 重算任务、运行和 split；对照人工 CSV 的第一轮非空标签、OpenJudge job ID 集合及 manifest 最新运行。下表数值与基线一致。无效评分单列，不进入人工比较。 | 通过 |
| 合成示例和全量测试 | 示例与 `--check` 均退出 0；另核对了三类 judgment、源文件哈希字段和盲标 ID 不进入轨迹输出。`make test` 退出 0，193 项通过；`make secrets` 退出 0，4 项通过。 | 通过 |

独立验收发现两个会影响数据解释的问题：重复 JSON 键可把人工判定接到错误轨迹；有限但越界的 OpenJudge 分数会计入人工分歧。修复前分别复现为错误发布和无效数少计，修复后由上述回归验证：前者拒绝发布，后者保留原评分行但标为异常，不参与比较。

## 真实本地重建

两份 manifest 共 111 行，按任务与配置取最新得到 93 次运行：87 次导出，6 次因未完成排除。6 次里有 2 次可沿用同题的 dev 分组，另 4 次没有任何已接纳的同题轨迹，列在未分配 split 中。跨 split 的任务数为 0。

| 范围 | 任务 | 轨迹 | 人工通过 | 人工失败 | 未标 | OpenJudge 行 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 全部 | 51 | 87 | 32 | 16 | 39 | 100 |
| dev | 41 | 70 | 26 | 14 | 30 | 82 |
| eval | 10 | 17 | 6 | 2 | 9 | 18 |
| flash-think-off | 51 | 51 | 18 | 7 | 26 | 54 |
| flash-think-on | 36 | 36 | 14 | 9 | 13 | 46 |

48/87 条轨迹有人工判定。37/87 条轨迹没有 OpenJudge 行；实际关联的 100 行均通过格式和分数范围检查，未发现未关联行。这里的“通过”是记录检查，不代表评分正确。配置组共享任务，因此配置组任务数不能相加。

当前版本号、输入摘要、产物 SHA-256、命令与退出码见本地 `.cache/trajjudge-data-p0/real-build-verification.json`；合成正反例命令见 `.cache/trajjudge-data-p0/demo-verification.json`。正式读取方式见 [README](../../../README.md#p2-trajectory-dataset)。

改动范围：`scripts/build_dataset.py`、`tests/test_dataset.py`、`samples/dataset_demo.py`、共享评分范围及其在 `src/trajjudge/judging.py` 的引用，以及 README 和本记录。沿用工作区已有的 `make dataset` 入口。P0 不验证外部样本授权、上游结果复验、真实评分效果或训练收益；P1–P3 留待各自验收。
