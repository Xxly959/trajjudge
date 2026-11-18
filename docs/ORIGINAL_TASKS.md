# TrajJudge P2 原创任务与验收

两道任务都提供版本 1 的可见题面、起始代码、合成输入、参考解和黑盒验收。另一种正确解由独立执行者只依据可见题面编写。部分错误解由一条明确的代码替换生成，替换前后的内容保存在各题的 `submissions/partial.json`。这些运行是构造提交的验收记录，没有采集真实模型交互轨迹。

| 任务 | 可见题面 | 重点验收 |
| --- | --- | --- |
| A · 轨迹事件汇总 | [event-summary/instruction.md](../tasks/original/event-summary/instruction.md) | 旧 attempt 的迟到事件保留计数，最新 attempt 的状态优先，相同事件只计一次。 |
| B · 评分结果关联 | [score-join/instruction.md](../tasks/original/score-join/instruction.md) | 对任务、运行和评分器版本作精确匹配。没有报告时写 `unknown`，报告中的 `error` 原样保留。 |

## 本地复现

实测环境为 macOS、Python 3.12.13。任务与 verifier 均只使用 Python 标准库。每次运行给各个提交复制同一份起始文件，每个黑盒用例再独立创建临时目录。运行器在 `matrix.json` 记录 Python 版本、起始文件与题面哈希、提交源码哈希、实现来源、验收退出码和 verifier 版本。verifier 版本由验收器与该题用例的内容哈希生成。

```sh
evidence_dir=$(mktemp -d)
.venvs/judge/bin/python scripts/run_original_task.py run event-summary --output "$evidence_dir/a"
.venvs/judge/bin/python scripts/run_original_task.py run score-join --output "$evidence_dir/b"
.venvs/judge/bin/python -m pytest tests/test_original_tasks.py -o addopts='' -q
make test
```

在每个提交的 `verification/` 查看实际交付的 `submitted-result.json`、逐项结果 `checks.json`，以及各用例实际产生的 `result.json` 和进程日志。若未产生文件，报告会保留对应的失败状态。

## 题面与验收对照

| 可见要求 | A 用例 | B 用例 |
| --- | --- | --- |
| 交付真实文件和实现 | `submitted-artifact` 核对文件字节，缺文件判失败 | 同左 |
| 第 1 条，输入结构 | 单次成功、空输入、非法 attempt、长整数、非法标识符 | 单次关联、空输入、重复版本、冲突运行 |
| 第 2 条，重复与冲突 | 等价重复投递、事件 ID 冲突、序号冲突 | 重复报告、孤立报告冲突、非法状态及标识符 |
| 第 3 条，业务结果 | 超时后重试、旧事件迟到、乱序 | 三个键分别碰撞、缺失版本写 `unknown`、保留 `error`、统计未请求报告 |
| 第 4 条，顺序与格式 | Unicode 排序、空输入、乱序等用例校验完整输出字节 | Unicode 排序、两个输入反序、空输入等用例校验完整输出字节 |
| 第 5 条，错误处理 | 非法 JSON、重复键、坏 UTF-8、缺输入、验证失败时保留原输出 | 同类异常，分别覆盖两个输入文件 |

## 运行矩阵

数字为通过检查数和总检查数。verifier 退出 0 表示通过，退出 1 表示提交未通过，退出 2 表示验收基础设施错误。矩阵命令在全部预期均匹配时退出 0。

| 提交 | A · 16 项 | B · 17 项 | 实际归因 |
| --- | ---: | ---: | --- |
| 起始版 | 4/16，退出 1 | 4/17，退出 1 | 保留了最简单的成功与空输入，重试或精确关联等检查失败。 |
| 参考解 | 16/16，退出 0 | 17/17，退出 0 | 实际产物与黑盒行为均符合题面。 |
| 独立正确解 | 16/16，退出 0 | 17/17，退出 0 | 由只读题面的独立执行者编写。 |
| 部分错误解 | 15/16，退出 1 | 16/17，退出 1 | A 错误拒绝相同事件的重复投递。B 把缺失报告写为 `fail`。 |
| 声称完成但无产物 | 15/16，退出 1 | 16/17，退出 1 | 代码通过所有黑盒用例，实际提交缺少 `result.json`。 |

每题在新的工作区重复两次。四次矩阵命令均退出 0，检查报告、JSON 产物和所执行源码逐字节一致。起始版的部分 Python 回溯带临时路径，原始日志分别保留。独立验收复跑了两题的正确解和部分错误解，并发现了 Python 长整数限制及缺失源码、证据目录不可创建时的归因问题。修复后，4301 位的合法 attempt 通过，缺少提交源码记为提交失败，无法创建证据目录记为基础设施错误。

另以 A 的同一份正确产物验证故障归因。原验收退出 0。仅把期望的唯一事件数改为 42，验收退出 1 且仅报 `artifact_mismatch`，说明错误来自修改的期望值。让用例文件发生语法错误，验收退出 2 并记录 `infrastructure_error`。相关输出存于本地 `outputs/original-tasks/p2/failure-attribution/`。

专项测试 6 项和全量测试 206 项均通过。实际结果位于本地 `outputs/original-tasks/p2/v1-run-a/` 与 `v1-run-b/`，命令、退出码和版本汇总见 `.cache/trajjudge-data-p2/verification.json`。

## Harbor 验证范围

```sh
harbor_dir=$(mktemp -d)
.venvs/judge/bin/python scripts/run_original_task.py package event-summary --output "$harbor_dir/event-summary"
.venvs/judge/bin/python scripts/run_original_task.py package score-join --output "$harbor_dir/score-join"
harbor run -p "$harbor_dir/event-summary" -a oracle
harbor run -p "$harbor_dir/score-join" -a oracle
harbor run -p "$harbor_dir/event-summary" -a nop
```

初次验收时 Docker daemon 未连接，先通过 TOML、Shell 语法和打包结构检查。后续启动 Docker Desktop，在独立环境安装 Harbor 0.25.0 后完成容器实跑，Docker 服务端版本为 29.7.2。两道题使用固定摘要的 Python 3.12.13 镜像，容器运行配置为无网络。

| Harbor 运行 | 奖励 | 核对结果 |
| --- | ---: | --- |
| A Oracle | 1 | 16/16，逐项报告和提交产物与本地参考解逐字节一致 |
| B Oracle | 1 | 17/17，逐项报告和提交产物与本地参考解逐字节一致 |
| A 空操作 | 0 | verifier 退出 1，缺少实际提交的 `result.json` |

三次 Harbor 作业均退出 0、无基础设施异常。作业、奖励和 verifier 记录保存在本地 `outputs/original-tasks/p2/harbor-oracle-a/`、`harbor-oracle-b/`、`harbor-nop-a/`，汇总见 `.cache/trajjudge-data-p3/harbor-verification.json`。[Harbor 任务配置](https://docs.harborframework.com/tasks/configuration) · [Oracle 方案](https://docs.harborframework.com/tasks/solution) · [验收入口](https://docs.harborframework.com/tasks/verifier)
