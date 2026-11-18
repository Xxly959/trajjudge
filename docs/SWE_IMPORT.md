# SWE-bench 多来源导入数据卡

这批数据用于检验 TrajJudge 能否将公开运行的轨迹、补丁、评测报告和测试日志按实例关联，并与本地 Claw-Eval 数据共存。SWE-bench 样本按结果均衡选取，不用于估算模型通过率。产物只在本地读取，未执行补丁、日志内命令或上游测试。

## 来源与选样

| 项目 | 固定版本 |
| --- | --- |
| SWE-bench Multilingual 登记 | [SWE-bench/experiments，40f164d](https://github.com/SWE-bench/experiments/tree/40f164d5b8f1d249bf95a6df8b74b577fd8e519d/evaluation/multilingual/20260902_mini-v2.4.6_gemini-3-5-flash) |
| 运行产物 | [SWE-bench 产物仓库，8dcca98](https://github.com/SWE-bench/20260902_mini-v2.4.6_gemini-3-5-flash/tree/8dcca98587e7f698753903e3b1747eb5dc013cb1) |
| 运行环境 | mini-SWE-agent 2.4.6，轨迹格式 `mini-swe-agent-1.1`，Gemini 3.5 Flash。评测器记录为 SWE-bench，具体版本未知。 |
| 本地 Claw-Eval | 从已通过哈希校验的 P0 快照读取，快照 ID 记入联合质检报告。 |

固定提交中有 264 个轨迹文件、258 个同时包含报告、补丁和压缩日志的目录。按文件名精确配对的交集为 256 个。未配对的 8 个轨迹文件中，6 个缺结果产物，另 2 个文件名重复带了后缀。后两条内嵌实例 ID 与其日志目录相符，当前导入规则未重命名它们。完整的未配对列表写入 `archive_inventory`。

先核对 Druid 的一条上游通过和一条失败，再从同时存在两种结果的仓库中按仓库名排序取前四个。每个仓库分别取按实例 ID 排序的首条通过和首条失败。两份官方登记文件中的结果都须一致。样本来自 Druid、Lucene、Axios 和 Babel，共 8 个实例。下载时，逐一对照固定 Git 树验证 32 个运行产物和 3 个登记文件的 Git blob ID。离线入口根据下载生成的 `bundle.json` 验证内容，来源身份由固定提交的获取步骤确立。

产物仓库的 GitHub 元数据没有标注许可证，固定文件树未见许可文件。外部原件和衍生轨迹放在忽略的 `outputs/` 下；公开示例完全由项目自造。来源细节见[第三方边界](THIRD_PARTY.md)。

## 字段映射

| 逻辑对象 | SWE-bench | Claw-Eval |
| --- | --- | --- |
| `task` | `instance_id` 对应命名空间、仓库、任务族和仓库分组。任务基线版本与任务时间为 `null`。 | P0 的 `task_id`、分类、难度、原 split，及记录的 Claw-Eval 版本。仓库和任务时间为 `null`。 |
| `trial` | 记录运行产物 revision、提交日期、harness 和运行状态。保留消息的角色、内容和工具调用字段。每个证据角色记录固定仓库、revision、路径、Git blob ID 和 SHA-256。 | 原 `trace_id`、agent 配置、消息、轨迹和 sidecar 路径及 SHA-256。 |
| `outcome` | `report.json` 的 `resolved` 和基础设施状态映射为 `pass`、`fail` 或 `infra_error`。记录报告标志、各测试分组成功和失败数，并保留报告、补丁和测试日志的引用。 | 使用 Claw-Eval 运行结果映射 `pass`、`fail` 或 `unknown`。 |
| `judgments` | 保存报告与登记的 `resolved` 两个字段。 | 保留人工、Claw-Eval 和 OpenJudge 三类判定。 |

未知字段记录名称，未映射的值仍可从本地原始证据追查。读取时比对轨迹和报告内嵌 ID、登记结果及轨迹里的提交与补丁字节，并检查压缩日志可解码。`outcome.reverified` 为 `false`，表示没有重新运行环境测试。

SWE-bench 全部归入 `external`，同仓库及同实例的记录同组。Claw-Eval 保留 P0 的按任务 split。已检查两来源各自的分组，跨 split 组数为 0，未发现完全相同的消息序列。缺乏跨来源任务映射与任务创建时间，因此跨来源任务族和时间隔离均记为未知。产物提交时间只描述该批运行。

## 复现与验收

```sh
# Public acquisition, into a new local directory
.venvs/judge/bin/python scripts/fetch_swe_bundle.py outputs/swe-import/pinned-bundle

# Offline import. Omit --claw-root for a SWE-only snapshot.
.venvs/judge/bin/python scripts/build_cross_source.py \
  --bundle outputs/swe-import/pinned-bundle --claw-root . \
  --output outputs/swe-import/combined

# Offline synthetic reproduction, including a separately runnable missing-file case
demo_parent=$(mktemp -d)
.venvs/judge/bin/python samples/swe_import_demo.py "$demo_parent/bundle"
.venvs/judge/bin/python scripts/build_cross_source.py \
  --bundle "$demo_parent/bundle" --output "$demo_parent/export"
rm "$demo_parent/bundle/logs/demo__project-1/test_output.txt.gz"
.venvs/judge/bin/python scripts/build_cross_source.py \
  --bundle "$demo_parent/bundle" --output "$demo_parent/export"
```

读取输出的 `CURRENT` 一次，再到同一 `snapshots/<ID>/` 查看 JSONL、质检与校验描述。缺件或证据错配按实例写入 `quality.json` 的排除项，命令退出 1。上面的合成示例先退出 0 导入 1 条，再退出 1 并记录 `missing_evidence`。测试另覆盖报告实例错配、提交错配、登记与报告不一致、Git blob 不一致、超出浮点范围的数字以及两来源原生 ID 相同。

| 输入 | 请求或覆盖 | 本地导入 | 排除与复验 |
| --- | ---: | ---: | --- |
| SWE-bench 选样 | 8 实例 | 8 轨迹，官方 4 通过、4 失败 | 0 排除，0 本地复验 |
| Claw-Eval P0 | 93 次最新运行 | 87 轨迹、51 任务、48 人工判定、100 OpenJudge 行 | P0 原有 6 次排除 |

固定来源获取与两次真实离线导入均退出 0。联合快照包含 95 条记录，两次生成的指针及文件字节相同。独立验收逐条核对 Claw-Eval 的消息、split 和判定，也复跑了合成正例、缺件和实例错配。验收发现过大 JSON 数字会让整个批次失败，现由回归验证其按实例排除。7 项专项测试和 `make test` 的 200 项全量测试通过。联合行结构版本为 1，快照格式版本为 2，命令与实际输入、输出哈希见本地 `.cache/trajjudge-data-p1/verification.json`。

一条真实的溯源路径是从 `swe-bench:multilingual:apache__druid-13704` 的 `outcome.evidence` 读取 `trial.evidence.report`，在本地与报告 SHA-256 `fb2d9aa6369a8d10b541a8f196890c2871005058ab2265a9846cd1a76792774d` 比对，再按 revision 和路径找到上游文件。[固定 revision 的报告](https://github.com/SWE-bench/20260902_mini-v2.4.6_gemini-3-5-flash/blob/8dcca98587e7f698753903e3b1747eb5dc013cb1/logs/apache__druid-13704/report.json)
