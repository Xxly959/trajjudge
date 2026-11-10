# TrajJudge 审核入口

这个项目将 Claw-Eval 轨迹转换为 OpenJudge 可读的消息序列，研究轨迹评分器与人工判断的一致性、重复运行稳定性，以及轨迹内提示注入对评分的影响。

## 建议阅读顺序

1. [README](README.md)和[中文走读](docs/WALKTHROUGH.md)介绍管线与离线环境。
2. [阶段一报告](reports/phase1.md)和[研究报告草稿](reports/FINAL_REPORT.md)列出结果、范围与局限。
3. [运行手册](docs/EXPERIMENT_RUNBOOK.md)和[执行记录](docs/APPROVED_RUNS.md)说明试验设置。历史运行所需的私有证据留在研究工作区。
4. [源码](src/trajjudge/)和[测试](tests/)可用于检查数据契约、实验执行及统计口径。按 README 固定两个上游版本后，运行 `make test` 和 `make secrets`。测试使用合成内容，模型调用由 mock 处理。

## 审核重点

- P2 的两个评分器都与 32/48 条人工标签一致。检查分母、全通过基线、类偏斜、单标注者及缺失复标对结论的影响。
- P3 有十条轨迹的 Flash Direct 试验，另有四条轨迹的策略及 Flash/Pro 对照。检查重复匹配、错误保留、缓存复用和置信区间。
- P4 有注入构造、配对统计、离线演练及规则对照。正式 LLM 注入实验暂缓，审核时把规则对照、演练和待测模型效果分开。
- OpenJudge 有一份独立的[补丁和 PR 草稿](contributions/openjudge/)，尚未向上游提交。

这是本地源码提交 `5c3dbe38c63c406ba6d2d59b0a4efe68c8d3ad90` 的公开快照。
快照保留代码、测试、汇总报告与复现文档。原始轨迹、人工标签、缓存与内部 Git 历史留在本地。公开仓库支持离线工程验证；历史模型结果需原始证据才能逐条复现。
