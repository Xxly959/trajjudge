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
| Phase 3 注入扩展 | **0**（已核实） | $0.000000 | $0.000000 | 1728 个 logical job（双臂）离线 replay 全命中缓存，score/status/reason 差异 0；见 §7 |
| Phase 4 阈值校准 | **0**（已核实） | $0.000000 | $0.000000 | LOSO 离线；100/100 原始输出从 `.cache/llm` 恢复并通过 token+分数双重身份校验；见 §8 |
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
| Phase 1 | 0 | $0.000000 | $0.000000 | 累计 guard $9.180483（未变） | 2026-11-13 |
| Phase 2 | 0 | $0.000000 | $0.000000 | 累计 guard $9.180483（未变） | 2026-11-13 |
| Phase 3 | 0 | $0.000000 | $0.000000 | 累计 guard $9.180483（未变）；余量 $5.000000 | 2026-11-13 |
| Phase 4 | 0 | $0.000000 | $0.000000 | 累计 guard $9.180483（未变）；余量 $5.000000 | 2026-11-13 |
| Phase 5 (`p5-neutral-l3-16`) | 32 | $0.079814 | ≈ $0.040 | 32/32 完成 | 2026-11-18 |
| Stage 3 (`stage3-grounded-flash-64`) | 38 (+2 次 402 零计费) | $0.123484 | ≈ $0.062 | 触发 HTTP 402 安全停机；累计 guard $9.383781 | 2026-11-18 |
| Phase 6（跨 vendor） | 0（待外部 Key） | $0.000000 | $0.000000 | 未启动（闸门 C） | — |

## 7. Phase 3 实测（2026-11-13，零花费）

| 项 | 值 | 证据 |
| --- | ---: | --- |
| 成本计划 logical job | 1,728 | `reports/phase3_dryrun_plan.json` |
| 成本计划 completions | 1,728 | 同上 |
| **冷启动峰值上限估算** | **$10.892966** | 字符估算，非账单；**超过 $5 硬上限** |
| 离线 replay 行数 | 1,728 / 1,728 | `outputs/p4/p4-phase3-replay-check.jsonl` |
| job 集合一致 / score·status·reason 差异 | True / **0** | `reports/phase3_scenario.json` → `dry_run.replay` |
| 缓存未命中 | **0** | replay 行中无 `cache miss` reason |
| 新增 ledger 记录 | 1,728，**全部 `cached=true`、`api_calls=0`** | `outputs/usage/usage.jsonl` 尾部 1728 条 |
| 累计 guard（`pricing_p3.yaml` 口径） | **$9.180483 → $9.180483（未变）** | `budget_cost(...)` 复算 |
| error 行（如实保留） | 27（防御 19 / 未防御 8，全部 comprehensive） | 同上 |

**结论：Phase 3 新增花费 $0.00，新增 API 调用 0。** 注入网格完全由既有缓存支撑。

⚠️ **冷启动重跑不可自行执行**：若缓存失效而需要真实重跑这 1,728 个 completion，
峰值上限估算 $10.892966 已超过 $5 硬上限（也超过 §2 的 $4.287588 总 guard 计划）。
按 §4.1 与硬约束，必须**先停下询问 owner**，不得直接跑，也不得自行缩小预注册范围来省钱。

记账口径提醒：guard 复算必须用 `configs/pricing_p3.yaml`（`scripts/experiment.py:147` 已如此覆盖）。
若误用默认的 `configs/pricing.yaml`（只含 `deepseek-flash`），ledger 中 48 条 `deepseek-v4-pro`
与 8 条 `model-discovery` 记录会让 `budget_cost` 返回 `None`，看起来像「历史花费未知」，实为定价表缺项。

## 8. Phase 4 实测（2026-11-13，零花费）

按 owner 要求，花钱相关数字一律并列**实际 token 推算**与**guard 保守口径**两个数。

| 项 | 实际 token 推算 | guard 保守口径 | 证据 |
| --- | ---: | ---: | --- |
| Phase 4 新增 completion | **0** | **0** | 纯离线：LOSO 校准 + 缓存恢复，无网络请求 |
| Phase 4 新增花费 | **$0.000000** | **$0.000000** | `reports/phase4_calibration.json` → `raw_recovery.api_calls = 0` |
| 累计 guard | $9.180483（未变） | $9.180483（未变） | 余量 $5.000000 |

**缓存依赖与冷启动反事实**（不是本阶段花费，只是把依赖风险量化）：

| 项 | 值 |
| --- | ---: |
| 恢复并通过双重身份校验的原始输出面板 | **100 / 100** |
| 依赖的缓存文件数 | 100（全部 `deepseek-flash`） |
| 这些面板的实际 prompt tokens | 849,260 |
| 这些面板的实际 completion tokens | 28,844 |
| **若缓存丢失需冷启动重跑**：实际 token 推算（off-peak） | **$0.144695** |
| **若缓存丢失需冷启动重跑**：guard 保守口径（peak） | **$0.289391** |

两个口径都远低于 $5 上限，因此 Phase 4 的缓存依赖**不构成预算风险**；
与 Phase 3 的 $10.892966 冷启动反事实（§7）不同，此处无需停下询问 owner。
单价取自 `configs/pricing_p3.yaml`（`deepseek-flash` off-peak 0.15/0.60，peak 0.30/1.20 USD per 1M）。

**身份校验口径**：tag 不唯一，故只接受 `prompt_tokens` 与 `completion_tokens` 同时匹配已记录 usage、
**且**按上游运算顺序复算的分数与已记录分数之差 ≤ 1e-9 的缓存条目；
两条都通过但内容不同 → 报「原始输出不可得（2 条缓存通过身份校验但内容不同）」，不猜选。
本阶段 100/100 唯一命中，无不可得条目。

## 9. Phase 5 预算批准状态（2026-11-14，owner 裁定，**尚未执行**）

owner 已批准 Phase 5 预算，但**批准不等于放行**：仍等闸门 A 通过、标签定稿后才启动。

| 口径 | 主对照（864） | 非饱和子集（90） | 合计（954 completions） |
| --- | ---: | ---: | ---: |
| **guard 保守口径**（peak，全 cache-miss） | $2.524608 | $0.262980 | **$2.787588** |
| **实际 token 推算**（按 P4 实测 published/guard = 9.49% 外推） | — | — | **≈ $0.265** |

两个数都在 $5 硬上限内；加上 Phase 6 预留 $1.500000 后总 guard 计划 $4.287588，余量 $0.712412（§2）。
**实际 token 推算是预估不是承诺**，跑完以 usage ledger 回填。

启动前必须依次完成（缺一不可）：
1. 闸门 A 通过：round1 两条空白处理完毕、两条金标准疑点由 owner 裁定、round2 完成并产出人类 test-retest κ。
2. 标签定稿；若标签有变，先重算 Phase 3/4 的 PROVISIONAL 数字并标注「标签 v2」。
3. **备份 `.cache/llm`**（备份完成前不得发起任何真实调用）。
4. 用届时最新的 `configs/pricing*.yaml` 复核单价，并把**实际 token 推算**与**guard 保守口径**两个数
   再次并列写入本文件；若重估后超 $5，停下询问 owner。
5. 先 `--dry-run`，确认调用数与预估一致后再真实调用；沿用正 `--cap-usd`、保存的累计 ceiling、
   resume 不 renew cap、exclusive run lock、原子 checkpoint、append-only usage ledger。

**本轮（CC-1 落地）新增花费 $0.000000 / 新增 API 调用 0**，累计 guard $9.180483 未变，余量 $5.000000。

## 10. CC-2 实跑前余额核验与聚焦预算表（2026-11-18）

开跑前通过 `/user/balance` 实测可用余额为 **CNY 1.08（≈ USD 0.15）**。按 `PREREG_v2.md §12 CC-2` 在发起任何新请求前冻结以下双批次计划：

| 批次 | 新增 completion | guard 保守估算 (peak) | 预期实际 token 估算 (含前缀缓存) | 阶段 `--cap-usd` |
| --- | ---: | ---: | ---: | ---: |
| `p5-neutral-l3-16`（聚焦中性对照） | 32 | $0.240927 | ≈ $0.045 | $0.45 |
| `stage3-grounded-flash-64`（改进版混合评分器） | 64 | $0.263118 | ≈ $0.046 | $0.55 |
| **合计** | **96** | **$0.504044** | **≈ $0.091（≈ CNY 0.65）** | 合计上限 $1.00 ≤ $5.00 硬上限 |