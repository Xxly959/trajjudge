# State recovery — 2026-11-05

This is a new inspection of source and local evidence, not an endorsement of
earlier completion claims. Recovery began at `a27643b` on `main`.

## Preservation and evidence

- `git status --short`: two modified files and one untracked script. No stash,
  no other local/remote branches. Recorded `git reflog -20`, `git log --stat -30`
  and the last three commits' diff. Recovered these three files in `10abb5e`
  (`wip: recovered uncommitted changes from previous agent`).
- Complete 1.5 GB backup: `<local-backup>`;
  `.git` presence verified before the recovery commit.
- `git check-ignore -v .env`: `.gitignore:2`; no tracked `.env`.
- `docker ps -a`: four exited, unrelated containers; no running containers.
  Process inventory found editor Python tooling only, no Claw/judge batch.
  Nothing was stopped or deleted. No `labels/` or `annotation/labels.csv` existed.
- Recent file times end with the hard-task batch at 2026-11-04 23:12 CST.
  Existing ignored chain scripts contain paid commands; they were not executed.
- `make test`: **147 passed in 5.30s**. Autouse socket denial and fake
  transports inspected. `rg 'TODO|FIXME|NotImplemented' src tests scripts`: none.
- Integrity scan of `outputs/`, `tests/`, `data/`, `.cache/llm`: **1,074 JSON,
  236 JSONL, 6,496 nonblank JSONL lines; zero parse failures** (before replay).
  No pending usage markers or cache temporary files. `DiskCache.put` already
  writes a same-directory temporary file then `os.replace`; no cache rewrite needed.
- `env -u DEEPSEEK_API_KEY make phase1`: exit 0, four cache hits, zero actual
  completions. Report SHA-256 before/after:
  `1eb5ca65ba3b7654353451bacebef97a12fe616574962556c163345869abd0b8`.
  This verifies local replay, not a newly provisioned clone. Dependencies and
  ignored raw evidence/cache are required; a source clone alone cannot replay.
- Both upstream worktrees clean: Claw-Eval
  `5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7` (MIT), OpenJudge
  `7d27246484e91c6ed4a349b6ebe7bd4629d9378f` (Apache-2.0).

## Delivery status at recovery

| Item | Status | Evidence and treatment |
| --- | --- | --- |
| S1 client/cache/budget/secrets | Verified complete locally | Cache/usage code, offline tests; retain |
| S2 endpoint/thinking/tool smoke | Verified stored evidence | `outputs/smoke/s2.json`, smoke tests; no new paid probe |
| S3 OpenJudge integration | Verified complete locally | Native grader replay and bridge tests |
| S4 Claw reconnaissance | Complete, live infrastructure not revalidated | `notes/claw_eval_recon.md`; source/hash/license inspected |
| S5 pilot | Verified stored evidence | Two traces + sidecars + manifest validated by phase1 |
| S6 four graders | Verified complete locally, schema gap | Eight replay rows; legacy runner lacks top-level repeat_id; repair next |
| S7 report | Verified local replay; fresh-clone acceptance not rerun | Identical report hash; no research conclusion |
| P2 dataset expansion | Partial, already exceeds count target | 87 completed traces / 51 tasks / 36 paired tasks; no further collection needed now |
| P2 strata/config freeze | Partial | 81 official passes / 6 failures; mixed output caps; freeze provenance before sampling |
| P2 annotation guide/tool | Partial | Existing CLI; truncation, non-atomic CSV saves and blind re-label ids need attention |
| P2 human labels/relabel | Not started | Owner only; never prefill |
| P2 agreement/baselines/CIs | Partial infrastructure | `agreement.py` + tests; no data join/report command or actual human comparison |
| P3 repeat/cache/strategy infrastructure | Partial | Mock tests; resume key omits input/model/token cap; append-only results lack atomic run manifest |
| P3 model/thinking/sampling probe | Not started as experiment | `probe_sampling.py` only; statistical evidence cannot establish server parameter semantics |
| P3 stability results/CIs/cost | Not started | No P3 result files; needs approved budget; pro unpriced |
| P4 templates/defense | Verified unit-tested infrastructure | Four benign templates, two insertion sites; no attack-effect result |
| P4 controls/paired analysis/results | Partial / not started | No execution/report driver; rule scores can change when lexical tool text changes |
| P5 upstream investigation | Partial | `OPENJUDGE_SURVEY.md`; raw-score clamping confirmed in pinned source |
| P5 branch/draft/contribution acceptance | Not started | No external authorization; prepare isolated local proposal only |
| P5 final report/README/resume/walkthrough | Partial / not started | Phase1 README exists; final research conclusions blocked by labels and paid runs |

## Dataset and configuration audit

Latest per-task manifests give thinking-off **51 complete** (47 pass / 4 fail),
thinking-on **36 complete** (34 pass / 2 fail). All 87 adapt without unmapped
content and have trace ends. Manifest pass flags agree with trace grading events.
Framework grades are DeepSeek regrades, not leaderboard truth or human labels.

Actual agent request sidecars establish distinct cohorts: off 2048 tokens (4
traces), off 4096 (47), on 4096 (27), on 16384 (9). Therefore thinking comparisons
are confounded by cap and task selection. Preserve every original trace; record
cohorts, and do not pool them as a controlled thinking ablation. D25's claim
that both caps are 4096 is stale. Multiple attempts and stopped runs are recorded;
latest complete task status is not the count of all attempted trajectories.

## Cost reconciliation

Before this recovery: 948 ledger rows, 68 cached; 879 uncached successes
(including model discovery), one `unknown_reconciled`. Token totals:
6,404,746 input + 649,380 output. Conservative peak/cache-miss estimate
**$2.700680**, of which P2 **$2.681012**, phase1 **$0.019668**.
The unknown call is an estimate, not recovered provider usage; original evidence
is retained in `outputs/usage/reconciliation.jsonl`. Replay adds only cached rows.

Read-only `GET /user/balance` returned available **[balance omitted]** on 2026-11-05 CST;
`GET /models` returned `deepseek-flash`, `deepseek-v4-pro`. No completion was sent.
Reference: https://api-docs.deepseek.com/api/get-user-balance/ . No opening balance,
top-up history, invoice, historical FX or other-client usage evidence is available.
Consequently the current CNY balance cannot reconcile estimated USD project spend
or prove that every historical charge was logged. No unlogged amount is invented.
No new paid budget is approved: ROADMAP estimates and shell command caps are not
owner approval evidence. All paid work remains gated.

## 前任意图推断

提交顺序与最近文件显示：先搭好 P2–P4 的基础模块，再扩大 P2，发现失败太少后
增加长任务。最后一次未提交变更提高 thinking-on 输出上限，可能为解决截断；
这一目的属于推断，不能当作已批准的实验变更。下一步很可能是挑选 50 条盲标、
启动 P3；目前没有实际标注包、P3/P4 结果或预算批准证据。旧 AUDIT 中关于
repeat_id 的一部分问题后来已修，旧文档不能代表现状。

## 我的继续计划

1. 保留现有数据、阈值、独立环境与上游版本，修复影响可信度/恢复能力的缺口。
2. 冻结含来源与配置分组的 P2 清单；交付 50 条可完整阅读的盲标包，空白标签，
   已有标注一律不覆盖；明确类别偏斜与选择偏差。暂不再扩充付费数据。
3. 补齐 P3 配置/输入身份校验、原子检查点与离线分析；实际重复运行等待预算。
4. 补齐 P4 执行/配对分析与规则对照；正式失败集合只能取 owner 人工标签。
5. 准备本地 OpenJudge 贡献草稿及证据受限的交付文档；对外动作和最终结论待确认。

Subsequent work and commands are checkpointed in `docs/PROGRESS.md`.

## Follow-up verification (after recovery)

At source commit `6088ebf`, a new `--no-hardlinks` source clone was tested with
no `.env`, outputs or response cache: **170 passed in 5.40s**. It reused installed
judge dependencies, not a newly provisioned virtual environment. The first
attempt preceded the documented sibling-source setup and had 23 missing-upstream
failures (Claw provider bindings, OpenJudge commit/sample lookups and grader
runners). After adding pinned read-only sibling links, tests passed; neither
assertions nor upstream source were changed for these setup failures.

Restoring only S5 evidence, usage and response cache then running phase1 with a
`sitecustomize` socket-deny guard and no key regenerated the identical historical
report hash. Logs: `outputs/verification/recovery-source-only-tests.log`,
`recovery-clone-tests.log`, `recovery-clone-phase1.log`.
An actual-key scan over 1,461 code/evidence/cache files found zero leaks;
`git log -p --all` contained neither the actual key nor key-like strings.

The independent review found two report defects (repeat truncation and
provenance-erasing deduplication); regression failures were observed and fixed.
Contribution checks include existing accuracy cases: 12 unit passed, two paid
quality tests deselected. No paid completion or external write occurred.
