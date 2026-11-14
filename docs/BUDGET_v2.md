# BUDGET v2 — 新增花费预估与硬上限

**硬上限：新增真实花费 $5.00。** 本文件采用**更严格**的口径：把保守 guard 总额也压在 $5 以内，
这样无论按 guard 还是按真实账单计算都不会越界。超出立即停下询问 owner。

计价依据：`configs/pricing.yaml`（2026-11-04 核验）与 `configs/pricing_p3.yaml`（2026-11-05 核验），
`deepseek-flash` peak/cache-miss：input $0.30/Mtok、output $1.20/Mtok；
off-peak：input $0.15/Mtok、output $0.60/Mtok。
单价来源为官方定价页，**不是**发票；provider 的 prompt-cache 与 off-peak 折扣会让真实账单更低。

## 1. 单价标定（来自 P4 实测，不是猜测）

P4 `p4-flash-human-fail-16`：1,728 logical jobs，48 命中缓存，**1,680 次新 completion**，
prompt 14,128,604 tokens、completion 508,592 tokens，peak guard **$4.848892**。
按 published off-peak 价并计入实测 cache-hit 份额后为 **$0.460284**，即 guard 的 **9.49%**。

P4 `defended=true` 行的平均 token 画像（用于 v2 预估）：

| grader | n | mean prompt | mean completion |
| --- | ---: | ---: | ---: |
| trajectory_accuracy | 432 | 10,083 | 116 |
| trajectory_comprehensive | 413 | 6,869 | 506 |
| **合计（加权）** | 845 | **8,512** | **307** |

→ **每次新 completion 的 peak guard = $0.002922**，off-peak all-miss = $0.001461。

## 2. 分阶段预算

| 阶段 | 新增 completion | peak guard | off-peak all-miss | 说明 |
| --- | ---: | ---: | ---: | --- |
| Phase 0 复核 | 0 | $0.000000 | $0.000000 | 只读，已完成 |
| Phase 1 统计口径 | 0 | $0.000000 | $0.000000 | 纯离线重算 |
| Phase 2 标注可靠性 | 0 | $0.000000 | $0.000000 | 人工标注，闸门 A |
| Phase 3 注入扩展 | **0**（预计） | $0.000000 | $0.000000 | estimate-only dry-run 已确认 864 个 off 臂 job 与 P4 完全一致；缓存覆盖待临时目录离线 replay 核对 |
| Phase 4 阈值校准 | 0 | $0.000000 | $0.000000 | LOSO 离线；per-step 原始分从 `.cache/llm` 恢复 |
| Phase 5 中性对照（主） | 864 | $2.524608 | $1.262304 | 16 轨迹 × 9 变体 × 3 重复 × 2 grader |
| Phase 5 非饱和子集 | 90 | $0.262980 | $0.131490 | 5 轨迹 × 9 变体 × 1 重复 × 2 grader，仅中性臂 |
| Phase 6 跨 vendor | 96 | **预留 $1.500000** | 待定 | 闸门 C 后按实际 vendor 定价重估 |
| **合计** | **1,050** | **$4.287588** | — | 上限 $5.00，**余量 $0.712412** |

Phase 6 的 flash 等价成本仅 $0.280512（96 × $0.002922）。预留 $1.50 是因为 vendor 未定，
非 DeepSeek 模型单价可能高数倍。**拿到 key 后必须先用该 vendor 的真实定价重估并更新本表，再开跑。**
若重估后总额超过 $5，停下询问 owner，不得自行扩大上限。

## 3. 真实花费预期

按 P4 实测的 **published 估算 / peak guard = 9.49%** 比例外推，Phase 5 的 954 次新 completion
真实账单约 **$2.787588 × 0.0949 ≈ $0.265**。
这是**预估**，不是承诺；实际以 usage ledger 为准，每阶段结束后如实回填。

## 4. 执行纪律

1. **先 dry-run / 离线回放，再真实调用。** Phase 3 必须先离线核对 864 个 job 全部命中缓存；
   若出现任何未命中，停下报告，不得自动转成真实调用。
2. 每阶段开跑前把预估成本与调用数写入本文件并 commit；跑完回填实际值。
3. 沿用既有 guard：正 `--cap-usd`、保存的累计 ceiling、resume 不 renew cap、
   exclusive run lock、原子 checkpoint、append-only usage ledger。
4. `--offline` 禁止 endpoint fallback；缓存缺失即停止执行。
5. 每阶段结束 commit 并更新 `docs/V2_LOG.md`，记录实际花费与余额快照。
6. **不得**为了省钱而删除 invalid 行、跳过重复次数或缩小预注册范围；
   范围变更必须回到 `docs/PREREG_v2.md` 走变更控制。

## 5. 已花费（v2 之前，不计入 $5 新增上限）

历史累计 guard accounting **$9.180483**（含历史预留），其中 P4 新增 $4.848892。
v2 的 $5 上限只约束**本次新增**，与历史账本分开记账，但沿用同一个绝对 ceiling 机制。

## 6. 回填区（每阶段结束后填写）

| 阶段 | 实际新 completion | 实际 guard | 实际 published 估算 | 余额快照 | 日期 |
| --- | ---: | ---: | ---: | --- | --- |
| Phase 0 | 0 | $0.000000 | $0.000000 | 未查询（只读阶段） | 2026-11-13 |
| Phase 1 | — | — | — | — | — |
| Phase 2 | — | — | — | — | — |
| Phase 3 | — | — | — | — | — |
| Phase 4 | — | — | — | — | — |
| Phase 5 | — | — | — | — | — |
| Phase 6 | — | — | — | — | — |