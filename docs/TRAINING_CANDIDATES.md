# TrajJudge P3 训练候选数据卡

P3 从本地原创任务的验收记录筛选完整示范和同题偏好对。v1 审核了 2 道任务的 10 份构造提交，验证了 4 份正确产物，但没有找到完整交互轨迹。因此 `sft.jsonl`、`preferences.jsonl` 和对应的 `provenance.jsonl` 均为零行。筛选分母、排除原因和原始证据引用保存在 `quality.json`。

| 数据来源 | 条数及用途 |
| --- | --- |
| P2 构造提交 | 10 份本地执行记录，包含 2 份最终回复和 0 份完整轨迹 |
| 真实模型运行 | 0 份 |
| 合成格式夹具 | 1 条 SFT 和 1 对偏好，单独用于验证 TRL 预处理 |
| 外部公开题和 Claw-Eval | 排除在本次原创训练候选范围之外 |

任务族分配在筛选前固定。轨迹事件汇总分配到训练，评分结果关联留作评测。相同任务族的变体须使用同一分配，配置中重复声明任务族或任务会被拒绝。真实批次的任务族交集为 0。这里检查的是项目登记的任务族，尚无跨公开数据的语义近重复检测。[任务族策略](../tasks/original/partitions-v1.json)

## 同批筛选对照

两种方法都以全部 10 份构造提交为分母。最终回复规则仅匹配这批样本中保存的固定句式「已完成修改并生成 result.json」，没有使用模型判断。

| 方法 | 入选 | 排除 |
| --- | ---: | --- |
| 只看最终回复 | 2/10 | 8 份无最终回复 |
| 核对实际产物和逐项验收 | 4/10 | 6 份未通过 |

两个集合没有交集。只看回复选中的两份都是声称完成但没有交付 `result.json` 的反例。通过产物核验的四份都没有保存最终回复。训练范围内有 2 份通过与 3 份失败，形成 6 个待筛组合，均因缺少完整轨迹排除。SFT 排除了 5 份评测族提交、3 份训练族未通过提交和 2 份训练族通过但缺轨迹的提交。

## 入选条件和来源链

- 核对任务版本、题面、起始文件、提交源码与 verifier 版本。再用已保存的实际产物、逐用例产物、进程退出码和验收预期复核结果。证据缺失、修改或超时保留为未知或排除。
- SFT 需要通过核验的完整轨迹。轨迹须关联提交和验收哈希，提示词与公开题面一致，工具调用有声明和必填参数，返回按调用 ID 与函数名关联，且存在最终回复。
- 偏好对要求同一训练任务、题面版本、起始环境、验收版本和工具定义。选中的轨迹通过核验，被拒绝的轨迹有具体的行为或产物失败。两条完成过程必须不同。模型名、thinking 设置或 LLM judge 不参与配对。
- 导出记录采用 TRL 的对话型 SFT 与显式 prompt 偏好格式。样本来源、筛选依据和哈希单列于 `provenance.jsonl`，通过文件名与行号关联。[TRL 数据格式](https://huggingface.co/docs/trl/dataset_formats) · [DPO 工具调用](https://huggingface.co/docs/trl/dpo_trainer#tool-calling-with-dpo)

如有新轨迹，把已保存的本地证据放在相应构造或真实运行记录中。版本 1 的 `trajectory.json` 包含 `schema_version`、`complete`、`source_id`、`origin`、`candidate_sha256`、`verifier_version`、`checks_sha256`、`artifact_sha256`、`messages` 和 `tools`。核验依赖可信的本地任务运行记录。哈希用于检验引用和保存内容的一致性。

## 复现和独立验收

```sh
p3_repro=$(mktemp -d)
.venvs/judge/bin/python scripts/run_original_task.py run event-summary --output "$p3_repro/p2/event-summary"
.venvs/judge/bin/python scripts/run_original_task.py run score-join --output "$p3_repro/p2/score-join"
.venvs/judge/bin/python scripts/build_training_candidates.py \
  --p2-root "$p3_repro/p2" --output "$p3_repro/candidates"
.venvs/judge/bin/python -m pytest tests/test_training_candidates.py -o addopts='' -q
```

真实的 P2 两次复跑各自导入一次，两次命令均退出 0，候选、质检及所有哈希逐字节一致。独立验收用临时合成证据重现 1 条合格 SFT 和 1 对合格偏好，确认错误的工具返回与跨 split 任务族会被拒绝。

| 独立验收发现 | 修复后结果 |
| --- | --- |
| 高优先级，`verified_outcome` 原先信任隐藏用例的状态汇总。改写已保存的隐藏用例产物后，仍会放行示范与偏好对。 | 用例的命令、退出码、实际产物和错误输出与正式期望重新比对。受影响的记录标为证据不一致，无法入选。 |
| 中优先级，`validate_conversation` 原先只检查参数是否为对象。省略必填参数也能被接受。 | 按函数定义检查必填参数，缺失时排除。 |
| 低优先级，缺少来源或回复编码错误会中止整批。 | 保留记录和比较分母，分别报告来源未知或回复无效。 |

5 项专项测试及 `make test` 的 211 项全量测试通过。

要单独复现格式验证，在独立环境中安装固定版本。演示用本地生成的小型配置和分词器，只初始化训练器和预处理输入。

```sh
format_dir=$(mktemp -d)
uv venv --python .venvs/judge/bin/python "$format_dir/venv"
uv pip install --python "$format_dir/venv/bin/python" \
  'trl==0.29.0' 'datasets==4.7.0' 'transformers==4.57.6' 'torch==2.15.0' 'jinja2==3.1.6'
"$format_dir/venv/bin/python" samples/verify_training_format.py "$format_dir/result"
```

已用 TRL 0.29.0 的 SFTTrainer 与 DPOTrainer 读取合成样本并生成 token。Dataset 往返保留工具参数、返回文本和调用关联，DPO 的 chosen/rejected 产生不同 token。该版本的 SFT 截断会尝试切片 Arrow JSON 类型的工具列，本次短样本用 `max_length=None` 完成预处理。真实训练模板、长度策略和训练收益均未实测。

实测产物位于本地 `outputs/training-candidates/p3-final-v1/` 与 `outputs/training-candidates/format-verified-v1/`。两次构建的命令、退出码和哈希见 `.cache/trajjudge-data-p3/verification.json`。
