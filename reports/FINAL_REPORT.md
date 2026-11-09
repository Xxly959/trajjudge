# Audit delivery report — incomplete research draft

Updated: 2026-11-09 CST. Owner review is required before publishing conclusions or
resume wording. This report distinguishes verified engineering and free lexical
controls from experiments that still require human work and approved API spend.

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
48 first-round labels. The local partial RQ1 report excludes the two blank items,
and the delayed human re-label round remains pending.

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

## Pending research

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

| Question | Current state | Required evidence |
| --- | --- | --- |
| RQ1 agreement | Partial comparison on 48 human labels | Two blank items and delayed re-label round remain pending |
| RQ2 stability | Ten-trace Flash Direct pilot completed; wider P3 pending | Broader sample and strategy comparisons within separately approved scope |
| RQ3 LLM injection | P4 report pending | Actual owner-fail set, budget, matched original/variant/defense repeats |
| Upstream contribution | Local branch + portable patch + draft | Owner authorization, maintainer review; acceptance is not established |

`make phase2 phase3 phase4` explicitly reports pending when data are missing.
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

Current cumulative reservation-inclusive guard amount: **$3.087352**. Original
actual usage for two attempts remains UNKNOWN; the ledger subtotal excluding
these attempts is $3.055441, still including an older reconciliation estimate.
Post-run balance CNY9.70 is not a per-request invoice.
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

The full completion definition remains unmet until the owner gates and actual
experiments above are complete. See [EXPERIMENT_RUNBOOK](../docs/EXPERIMENT_RUNBOOK.md)
for exact commands and unapproved budget proposals.
