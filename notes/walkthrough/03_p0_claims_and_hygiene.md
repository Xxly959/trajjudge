# 讲解卡 03 · 唯一口径总表（P0-1）与仓库卫生（P0-5）

## 1. 改了什么、为什么改

### P0-1 统一口径与同步上游贡献
- **改了什么**：
  - 新建唯一事实来源 [docs/CLAIMS.md](../../docs/CLAIMS.md)：每一项对外引用的数字都列出 `Claim ID`、分子/分母、独立场景数、95% 场景簇 CI、检验方法、定性标签（`deterministic` / `confirmatory` / `exploratory` / `provisional` / `retracted`）以及来源 JSON。
  - 统一降调规则：分母 `< 30` 禁用“倍”字（如把“提升 3 倍”改成 `1/14 → 3/14`）；CI 跨 0 或人工 `κ < 0.60` 的结论全部明标 `exploratory`；删除“彻底”“证伪”等夸大措辞。
  - 同步 OpenJudge 上游最新状态：**PR #246 与 PR #248 均已合入官方主干，Issue #247 已关闭**，并将 `contributions/openjudge/` 下未提交的补丁与文档提交入库。
  - 全面同步 [README.md](../../README.md)、[README_en.md](../../README_en.md)、[FINAL_REPORT_v2.md](../../reports/FINAL_REPORT_v2.md) 与 [showcase.html](../../reports/showcase.html)，确保四处数字完全一致。

### P0-5 仓库卫生与 30 秒可读性
- **改了什么**：
  - 将历史过程文档（`STATE_RECOVERY.md`、`CONTINUATION_PLAN.md`、`PROGRESS.md`、`APPROVED_RUNS.md`、`V2_LOG.md`）统一迁至 `docs/archive/`（并同步更新 `tests/test_phase4_analysis.py` 的日志路径）。
  - 压缩 `README.md` 与 `README_en.md` 首屏：一句话定位 + 3 条核心发现 + 1 张图（`fig5`）+ 快速开始，并在文末加上 AI 协作声明。
- **为什么改**：面试官点开 GitHub 仓库通常只花 30 秒。如果首屏堆满过程术语（`owner`、`PREREG` 细节、`STATE_RECOVERY`）或夸大倍数，第一印象会扣分；把过程文档归档、把核心口径收敛进 `CLAIMS.md`，既显得克制专业，又经得起逐行溯源。

---

## 2. 验收自检命令

运行下面两条命令，随时确认仓库口径干净、离线测试全绿：

```bash
git grep -nE "倍|彻底|证伪|黄金组合" -- README.md README_en.md reports/FINAL_REPORT_v2.md
make secrets && make test
```

---

## 3. 面试官可能怎么追问 & 参考回答

1. **追问：“你提到了 AI 编程助手辅助实现，那你自己真正做了什么？”**
   - **参考回答**：“我用 coding agent 加速代码实现和脚本编写，但实验设计、统计口径校验和结果复核是我自己主导的。最直接的例子是项目里记录的三次主动撤回/纠错：v1 发现中英译本伪重复并撤回 75% 翻转率、P0 复核源码发现正则模板泄漏并撤回 6.25% 防御结论（D30）、以及查对 JSON 时抓出 LOSO 图表键名错误导致的 62.5% 误杀率笔误（R-03）。只靠自动生成代码是不会主动推翻自己好看数字的。”

---

## 4. 留给你自己动手的小改动（约 10 分钟）

1. 通读 [docs/CLAIMS.md](../../docs/CLAIMS.md) 的第 2 节和第 6 节（已撤回记录）。
2. 挑出你打算写进简历的 3 个数字，合上屏幕口头复述一遍它们的**分子/分母、独立场景数、定性状态**和**为什么不能写成“提升 N 倍”**。
