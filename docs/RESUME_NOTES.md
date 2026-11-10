# Resume evidence — draft for owner review

No wording here is approved for a final resume. Engineering checks, exploratory
rule behavior and completed research are kept distinct.

## Supported material

- Built a local trajectory-to-grader integration with loss-aware adaptation,
  request caching, usage accounting, budget guards and offline replay. This work
  wraps existing Claw-Eval and OpenJudge; their graders, prompts, formulas and
  benchmark tasks are upstream contributions, not original inventions here.
- Recovered 87 completed real-model task trajectories across 51 tasks, including
  36 on/off task pairs. Counts come from the latest per-task records in
  `outputs/claw_eval/p2/{flash-think-off,flash-think-on}/manifest.jsonl`, checked
  against native trace grading events and request sidecars.
  These use benchmark sandbox/mock services, not production user tasks.
- Scored 50 frozen traces with two native LLM graders: 100 valid verdicts;
  source `outputs/p2/p2-deepseek-flash.jsonl`, reproducible from response cache.
  Valid schema/scale checks do not mean human agreement or correct grading.
- Single-case sampling probe: 18 observations, 15 valid/3 errors; 17 new
  completion calls plus one inherited P2 cache sample. Source `reports/probe.json`
  and `outputs/probe/probe-deepseek-flash.jsonl`. This is not a formal stability result.
- Froze 50 blind annotation items across 36 tasks. On the 48 owner-labeled
  items, both graders matched 32 judgments (66.7%), equal to always-pass.
  They missed 15/16 and 16/16 human failures, respectively. The two blank items
  and the unrun re-label round are recorded in [the P2 report](../reports/p2.json).
- Ran a ten-trace Flash Direct stability pilot. Of 120 planned results, 119
  were valid and one failed step coverage validation. No verdict flipped
  across the 39 complete repeat panels, while Comprehensive scores varied in
  16 of its 19 complete panels. The [pilot report](../reports/p3-flash-direct-pilot.json)
  includes group denominators and intervals.
- Compared Flash and Pro Direct on four matched trajectories and tested
  Flash's three evaluation strategies on shared draws. Both batches
  reproduced all 192 rows from cache, including seven invalid rows.
  Flash and Pro differed on 1/45 valid matched Direct verdicts. See the
  [Flash report](../reports/p3-flash-strategies-4.json) and
  [Pro report](../reports/p3-pro-direct-4.json).
- Ran 900 deterministic, free rule evaluations (100 originals and 800 variants).
  Among 400 variants per grader: loop score changed in 0, lexical information
  gain in 177. Source: `outputs/controls/controls-deepseek-flash.jsonl` and
  `reports/controls.json`. This is lexical sensitivity, not LLM attack success.
- Executed the 1,728-job Flash Direct perturbation batch on 16 human-labeled
  failures. It yielded 1,701 valid verdicts and 1,496 valid original–variant
  pairs. Undefended Accuracy flipped 18 of 24 baseline-fail pairs, derived
  from only three distinct baseline failures. The wrapper's denominator
  came from a different baseline set. See [the P4 report](../reports/p4.json)
  and [the execution record](APPROVED_RUNS.md) for coverage and intervals.
- Prepared a small local OpenJudge raw-score metadata fix with six mock
  regressions. Source: `contributions/openjudge/PR_DRAFT.md` and the tracked patch.
  It is not submitted or accepted.

## Candidate wording, pending owner approval

“Built a reproducible audit pipeline connecting Claw-Eval trajectories to
OpenJudge, with budget guards, recoverable runs and offline replay. Compared
two LLM graders with 48 blind human labels and found that both matched an
always-pass baseline, with 15/16 and 16/16 human failures missed.”

“Ran a ten-trajectory stability pilot with 120 planned scores. Reproduced
119 valid scores and one validation error from cache. Observed zero
pass/fail flips across 39 complete three-repeat panels.”

The owner reviews the wording and aggregate figures before public use. The
[run record](APPROVED_RUNS.md) preserves costs, coverage and execution details.

## Unsupported claims

Do not claim improved agent performance, reliable judgments, model robustness,
effective injection defense, statistical significance, a controlled thinking
effect, cross-vendor generalization, leaderboard comparability, or accepted
upstream contribution. Tests demonstrate engineering behavior under synthetic
inputs, not any of those research outcomes.
