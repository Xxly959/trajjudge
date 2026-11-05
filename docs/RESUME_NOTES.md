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
- Prepared 50 blank blind annotation items across 36 tasks, with immutable source
  hashes and owner-only labels. Source: `outputs/p2/annotation_meta.json`,
  `outputs/p2/annotation_set.json`, `annotation/labels.csv`. These are selected
  traces, not 50 human annotations. Do not put human-label totals on a resume yet.
- Ran 900 deterministic, free rule evaluations (100 originals and 800 variants).
  Among 400 variants per grader: loop score changed in 0, lexical information
  gain in 177. Source: `outputs/controls/controls-deepseek-flash.jsonl` and
  `reports/controls.json`. This is lexical sensitivity, not LLM attack success.
- Prepared a small local OpenJudge raw-score metadata fix with six mock
  regressions. Source: `contributions/openjudge/PR_DRAFT.md` and the tracked patch.
  It is not submitted or accepted.

## Candidate wording, pending owner approval

“Implemented a reproducible audit pipeline connecting Claw-Eval trajectories to
OpenJudge, with budget-aware model IO, independent repeat sampling, recoverable
run manifests and offline analysis. Prepared blinded human annotation and
defensive perturbation experiments with task-cluster confidence intervals.”

Only add completed human agreement, stability or LLM injection numbers after
the owner labels data, approves real runs and reviews the final report. Current
conservative historical cost is $2.700680, not an exact invoice; see STATE_RECOVERY.

## Unsupported claims

Do not claim improved agent performance, reliable judgments, model robustness,
effective injection defense, statistical significance, a controlled thinking
effect, cross-vendor generalization, leaderboard comparability, or accepted
upstream contribution. Tests demonstrate engineering behavior under synthetic
inputs, not any of those research outcomes.
