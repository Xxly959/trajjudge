# Audit delivery report — incomplete research draft

Updated: 2026-11-10 CST. Owner review is required before publishing conclusions or
resume wording. This report separates engineering verification, rule controls
and live LLM results. The delayed annotation repeat remains outstanding.

## Verified scope

The phase1 integration replays two real task traces through two LLM and two rule
graders from cached responses. `make phase1` regenerates the same historical
report hash recorded in STATE_RECOVERY; it does not rerun an agent. The offline
test suite tests synthetic/mock behavior, not judge quality. Source-only checkout
testing and raw-evidence replay have different prerequisites.

At recovery, P2 has 87 complete trajectories, 51 tasks, 36 paired tasks, 81
framework passes and six framework failures. Every completed trace adapts without
unmapped content and matches its native grading event. Actual request sidecars
show four output-cap cohorts; task and cap confounding preclude a causal thinking
comparison. See STATE_RECOVERY for exact counts and file paths.

50 blind annotation items are frozen across 36 tasks. The selection contains
all six framework failures and 44 framework passes; this enrichment, category
imbalance and the single annotator limit external validity. The owner submitted
48 first-round labels. The partial RQ1 report excludes the two blank items,
and the delayed human re-label round remains pending.

## P2 agreement on submitted labels

Both graders matched 32/48 owner labels (66.7%), the same as the always-pass
baseline. Of 16 human failures, Accuracy marked 15 as pass and Comprehensive
marked all 16 as pass. Accuracy also marked one human pass as fail. Cohen's
kappa was 0.04 for Accuracy and 0.00 for Comprehensive. The task-cluster
95% intervals for agreement were 51.1–81.6% and 52.9–80.4%, respectively.
[The P2 report](p2.json) includes category results, the framework comparison,
baselines and confidence intervals. The two blanks and the unrun re-label
round limit the scope of this comparison.

## Free rule-control experiment

Defensive threat model: append a benign grading-related note to a tool result or
assistant text. Four escalating templates and two locations produce eight variants
per trace. No payload targets an external system. Original messages remain intact.

Run `make rule-controls` to reconstruct the local numeric report from frozen
messages (or reuse per-job rule caches). There are 50 ×9 ×2 = **900 evaluations**:
100 original scores plus 800 variant scores. For each rule there are 400 paired
variants. Loop detection changed in **0/400**; lexical observation information
gain changed in **177/400**. These are exact descriptive counts over this selected
set. Per-variant signed score inflation and task-cluster 95% bootstrap intervals
are in [controls.json](controls.json); repeated variants are not independent samples.

The information-gain grader uses lexical overlap, so adding text can change its
score without it following any instruction. The unchanged loop scores are a
structural control on this sample, not proof that all rule graders resist all
perturbations. This run includes all selected traces, not an owner-labeled failure
cohort. It supplies no LLM injection-success rate or evidence that the optional
untrusted-data wrapper works.

Raw source: `outputs/controls/controls-deepseek-flash.jsonl`;
checkpoint: `runs/controls-deepseek-flash/manifest.json`;
templates: `src/trajjudge/perturb.py` at the project commit in Git history.

On the matched 16 human-fail trajectories, loop scores changed in **0/128**
and lexical information gain changed in **56/128** paired variants. This
subset comes from the existing rule-control rows and uses the same grouping.
The [matched report](p4-human-fail-rule-controls.json) contains task-cluster
intervals for score changes.

## P4 paired LLM perturbation experiment

The DeepSeek Flash Direct batch used 16 owner-labeled failures, two graders,
three repeats, eight perturbations, and two defense settings. The two blank
items were excluded. All **1,728** planned jobs produced records. Of these,
**1,701** passed validation and **27** Comprehensive outputs failed validation.
There were **1,496/1,536** valid original–perturbation pairs. The numeric report
marks coverage partial. Invalid rows are retained in the local run evidence.

| Grader | Wrapper | Valid pairs | Score changed | Fail-to-pass among baseline-fail pairs |
| --- | --- | ---: | ---: | ---: |
| Accuracy | Off | 384/384 | 47 | 18/24 |
| Accuracy | On | 384/384 | 22 | 7/8 |
| Comprehensive | Off | 376/384 | 354 | Undefined (0 eligible) |
| Comprehensive | On | 352/384 | 305 | Undefined (0 eligible) |

Each original can enter eight pairs. Accuracy's 24 and eight eligible pairs
come from three and one distinct baseline failures, respectively, out of 48
original evaluations per setting. The denominators differ, so the two flip
counts do not establish a wrapper benefit. Every valid Comprehensive original
passed (48 without the wrapper, 46 with it). The failure-to-pass rate is
undefined for Comprehensive even though its scores changed.

For the unwrapped Comprehensive grader, the level-three notice in a tool
result raised the trace-averaged score by **0.054** on its 0–1 scale
(task-cluster bootstrap 95% CI **[0.032, 0.080]**). This is one of eight
variant contrasts on a small, failure-enriched cohort. The
[P4 aggregate](p4.json) gives all per-variant effects, intervals and
denominators. Raw source: `outputs/p4/p4-flash-human-fail-16.jsonl`.

## P2 execution and sampling probe

Approved execution update: the P2 main judge now has **100/100 valid verdicts**
(50 traces × two graders). Human agreement is assessed separately on the 48
submitted labels. The one-case sampling probe has 18
observations, **15 valid /3 errors**, from 17 new API completions plus one P2
cache reuse. All three errors are thinking-off/temperature=1.5: two schema-field
failures and one capped completion. Other groups have three valid scores each.

All valid probe scores are 3. Temperature requests received model responses,
but this does not prove server parameter semantics. Thinking caps differ
(off1,024/on4,096), the sample is one trajectory, and a baseline observation was
reused from P2. No significance or general stability/quality conclusion follows.
Raw source: `outputs/probe/probe-deepseek-flash.jsonl`; aggregate:
[probe.json](probe.json). Cache replays reproduce all 100 P2 and 18 probe outcomes,
including errors, with zero API calls. Run details: [APPROVED_RUNS](../docs/APPROVED_RUNS.md).

### P3 Flash Direct pilot

Ten fixed traces × two graders × two thinking modes × three repeats produced
120 rows. Of those, 119 were valid and one was rejected for incomplete tool-batch
coverage in the returned step evaluations. The pilot reused 25 earlier
completions and obtained 95 new ones.

| Grader | Thinking | Complete three-repeat panels | Panels with score variation | Panels with verdict flips |
| --- | --- | ---: | ---: | ---: |
| Trajectory Accuracy | Off | 10/10 | 0/10 | 0/10 |
| Trajectory Accuracy | On | 10/10 | 0/10 | 0/10 |
| Trajectory Comprehensive | Off | 10/10 | 8/10 | 0/10 |
| Trajectory Comprehensive | On | 9/10 | 8/9 | 0/9 |

All 59 valid Comprehensive results were above the pass threshold. Its
zero-flip count therefore describes stable decisions on this sample alongside
score variation. The small fixed sample, shared provider and different
output caps limit inference about thinking and general stability. The
[pilot report](p3-flash-direct-pilot.json) preserves coverage and task-cluster
intervals. Source: `outputs/p3/p3-flash-direct-pilot.jsonl`.

### P3 matched strategy and model comparisons

The four-trace follow-up compared Flash Direct, Average and Voting on shared
draws, and Flash and Pro in Direct mode. Flash produced 139 valid rows out of
144 and Pro produced 46 out of 48. Across complete panels, Flash Accuracy
voting and Pro Direct Accuracy each flipped on one of four traces with
thinking off. Other settings showed zero within-panel verdict flips.
Flash and Pro Direct disagreed in 1 of 45 valid matched verdict pairs.
Flash and Pro Comprehensive respectively passed all 67 and 22 valid
results, with score variation in both models.

The comparison uses a fixed four-trace cohort with different output caps by
thinking mode. Both Pro errors hit the thinking-on Comprehensive cap. The
Flash strategy results share draws and their errors can share a single
completion. The [Flash report](p3-flash-strategies-4.json) and
[Pro report](p3-pro-direct-4.json) include group coverage and task-cluster
intervals.

| Question | Current state | Required evidence |
| --- | --- | --- |
| RQ1 agreement | Partial comparison on 48 human labels | Two blank items and delayed re-label round remain pending |
| RQ2 stability | Ten-trace Flash pilot and four-trace paired follow-up completed | The results describe the fixed cohorts and tested configurations |
| RQ3 LLM injection | All 1,728 planned rows collected with 27 invalid outputs and 1,496 valid pairs | The 16-trace study estimates effects within the tested configurations; sparse baseline failures limit the defense comparison |
| Upstream contribution | Local branch + portable patch + draft | Owner authorization, maintainer review; acceptance is not established |

`make phase2` rebuilds the main agreement report. Use the runbook's named
inputs for the executed P3 and P4 batches.
Offline reports cannot create absent experiments. Missing/error scores remain
null with coverage counts; reports derive repeat panels and identities from the
run manifest. RQ1 includes trivial baselines, confusion, kappa and AUC; stability
includes SD, flips and rank/decision agreement; injection pairs baseline and
variant within trace/config/repeat. Task-cluster bootstrap keeps both agent
configurations and repeated measurements together. Small or single-class samples
can yield undefined or degenerate intervals; none establishes significance.

## Cost and provenance

At recovery, the historical conservative subtotal was **$2.700680**, including
one `unknown_reconciled` estimate (P2 $2.681012, phase1 $0.019668). Approved execution
added conservative budget costs P2 **$0.321302 /$0.80** and probe
**$0.065370 /$0.20**, combined **$0.386672 /$1.00**. This includes request-bound
reservations for two unknown attempts, not fabricated measured tokens.

The P3 pilot added **$0.342380 / $1.50**. Cumulative guard accounting including
reservations reached **$4.331591** after the matched follow-up, which added
**$0.901859 / $4.00**. Actual usage for two historical attempts remains
unknown. The provider balance was recorded separately after the Pro run.
P4 added **$4.848892** on the conservative guard, for **$9.180483**
cumulative including historical reservations. The P4 usage-based estimate at
published off-peak prices is **$0.460284** with provider prompt-cache hits
counted at the published hit rate.
Discounts, other account activity and exchange rates prevent exact reconciliation.
See APPROVED_RUNS for unchanged ceilings, evidence and the separate budget policy.

Pinned read-only dependencies: Claw-Eval
`5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7`, MIT; OpenJudge
`7d27246484e91c6ed4a349b6ebe7bd4629d9378f`, Apache-2.0.
Agents and judges share the DeepSeek family, so self-preference and single-vendor
bias cannot be isolated. These scores must not be compared to Claw-Eval's
official leaderboard. Prices were checked on the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/);
balance endpoint documentation is [Get User Balance](https://api-docs.deepseek.com/api/get-user-balance/).

The OpenJudge draft preserves pre-bounding raw-score metadata with six mock
regressions. It changes no public final-score behavior or prompt, introduces no
new grader, and makes no measured grader-quality claim. See the
[contribution draft](../contributions/openjudge/PR_DRAFT.md).

## Evidence availability

Code, synthetic tests, numeric reports and the contribution patch are tracked.
Raw trajectories, response cache, usage, run checkpoints, annotation text and
owner labels remain local and ignored. Source hashes and private correspondence
are frozen locally. Preserve the backup and these artifacts for interview-time
reproduction; a Git clone alone does not contain them. Public artifact release
needs a content/rights review; benchmark code licensing alone does not establish
all rights in model-generated text.

The human repeat and owner review of the final wording remain open. See the
[experiment runbook](../docs/EXPERIMENT_RUNBOOK.md) for reproduction commands.
