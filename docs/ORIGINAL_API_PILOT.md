# 原创任务的 DeepSeek API 轨迹采集试跑

首批只用训练族的「轨迹事件汇总」。从同一起始环境采集两次，使用项目已配置的官方 DeepSeek API 和 `deepseek-flash`，关闭 thinking，温度分别为 0 和 0.35。评测族「评分结果关联」保留原 P2 证据用于数据分区检查。首批用于检验真实工具交互能否进入 P3 筛选。

每次最多 6 轮，每轮最多 2,048 个输出 token，失败的请求不自动重试。请求体上限 14,000 字节。按项目的预算算法和 2026-11-11 核对的高峰价，12 次全部用满的保守估算为 **0.0946368 美元**，建议授权上限 **0.10 美元**。[DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)

模型接收可见题面、公开的合成起始文件、原生工具调用及返回。提交工具只接受单文件 Python 实现。每次运行只挂载临时题目目录，容器无网络。正式验收用同版本的本地 P2 verifier 与逐项期望，隐藏用例和其结果留在本地。原始 API 响应、工具调用 ID、产物、预算、使用量和 verifier 结果保存到本次输出目录。

```sh
# Offline estimate
.venvs/judge/bin/python scripts/run_original_api_pilot.py

# Mocked API responses, real Docker and verifier
.venvs/judge/bin/python scripts/run_original_api_pilot.py \
  --rehearse --run-id original-api-rehearsal-v2 \
  --output outputs/original-api-pilot/rehearsal-v2

# Run after owner approves the exact cohort and cap
.venvs/judge/bin/python scripts/run_original_api_pilot.py \
  --run --run-id original-api-v1 --cap-usd 0.10 \
  --output outputs/original-api-pilot/original-api-v1

# Audit and export the captured evidence
.venvs/judge/bin/python scripts/build_training_candidates.py \
  --p2-root outputs/original-api-pilot/original-api-v1/evidence \
  --output outputs/original-api-pilot/original-api-v1-candidates
```

预算授权遵循项目运行手册。试跑分开记录成功、缺产物、调用截断和 API 错误。样本是否进入候选由可核验产物与完整轨迹共同决定。[实验运行手册](EXPERIMENT_RUNBOOK.md#budget-plan-and-approval-status)

## 2026-11-11 实跑记录

按聊天确认的 **0.10 美元**上限启动 `original-api-v1`。账本记录 6 次成功的真实 API 请求、0 次缓存命中、9,999 个输入 token 和 4,687 个输出 token。按高峰及缓存未命中单价保守核算为 **0.008625 美元**。账本无未结算请求。

| 运行 | 实际产物 | 验收 | 轨迹 |
| --- | --- | --- | --- |
| `flash-greedy` | 生成 `result.json` | 15/16，4301 位 attempt 的合法输入返回 2，预期为 0 | 完整，含工具调用、工具返回和最终回复 |
| `flash-sampled` | 第二次提交也生成 `result.json` | 15/16，同一长整数用例失败 | 最后一轮请求体为 17,868 字节，超过本地 14,000 字节上限，未发送请求，无最终回复 |

两条提交均触发 Python 的整数字符串位数上限。第二次的原始状态名为 `api_error`，实际错误由本地请求大小保护产生。采集命令因此退出 1，保留两个运行的源码、产物、响应与验收证据。P3 导入命令退出 0，核验了两个真实运行和五份评测族构造提交，导出 **0 条 SFT、0 对偏好**。两个真实运行的产物哈希和三个空导出文件的哈希均已独立重算。

实跑与账本见本地 `outputs/original-api-pilot/original-api-v1/`。候选和质检见 `outputs/original-api-pilot/original-api-v1-candidates/`。

## 继续采集与评测族基线

`original-api-v2` 在同一 **0.10 美元累计上限**下继续，先核验并复制上一轮已结算的用量账本。开始前高峰价保守剩余为 0.091375 美元。DeepSeek 客户端在每次请求前按同一上限做费用预留。

训练族安排两次独立运行。提交后可收到一个依据公开题面构造的 4501 位整数用例的结果，用于修正实现。该用例与正式验收的 4301 位用例分开，API 不接收正式 verifier 的用例或输出。评测族安排一次独立基线，只反馈原有可见输入的运行结果。请求大小上限放宽到 26,000 字节，仍按累计费用上限控制。局部请求超限单独记为 `local_request_size_limit`。

```sh
.venvs/judge/bin/python scripts/run_original_api_followup.py
.venvs/judge/bin/python scripts/run_original_api_followup.py --run
.venvs/judge/bin/python scripts/build_training_candidates.py \
  --p2-root outputs/original-api-pilot/original-api-v2/evidence \
  --output outputs/original-api-pilot/original-api-v2-candidates
```

续跑和导出均退出 0。训练题的两条轨迹都在首次提交后收到公开用例失败反馈，修正后通过正式验收。评测题的基线通过全部检查，按任务族策略排除出训练候选。

| 范围 | 真实运行 | 正式验收 | 进入 SFT |
| --- | ---: | --- | ---: |
| 轨迹事件汇总，训练族 | 2 | 各 16/16，均有完整轨迹 | 2 |
| 评分结果关联，评测族 | 1 | 17/17，有完整轨迹 | 0 |

没有同一设置下的已验证失败轨迹可配对，偏好导出为 0。第一轮的失败轨迹使用了不同的反馈设置，继续保留在第一轮证据中。对续跑证据重新导出，候选和质检逐字节一致。两条真实 SFT 候选均通过 Hugging Face Dataset 读取、工具调用结构检查及 TRL 0.29.0 的聊天模板预处理。未执行训练或测量训练收益。

续跑发送 11 次真实请求，24,587 个输入 token、8,437 个输出 token。两轮共 17 次请求，按高峰及缓存未命中单价从合并账本核算为 **0.026125 美元**，低于累计上限 0.10 美元。续跑原始证据与账本位于本地 `outputs/original-api-pilot/original-api-v2/`，候选位于 `outputs/original-api-pilot/original-api-v2-candidates/`。全量测试 214 项通过。
