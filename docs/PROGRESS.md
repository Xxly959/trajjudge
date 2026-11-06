# Progress

## Execution checkpoint — 2026-11-06 CST

- Current: P2 stopped on unknown accounting; 20/100 successful jobs preserved. Probe not started. No live runner remains.
- Pre-batch estimates: P2 100 calls / peak $0.630398; probe 18 calls / peak $0.144169. Approval and exact commands: APPROVED_RUNS.md.
- Last result: 170 project tests; fresh source-only clone also 170; guarded phase1 replay identical. Contribution: 12 unit passed, 2 quality deselected.
- Next owner action: label 50 blind traces. Other P3/P4 and external-action budgets remain unapproved.
- Next agent action: reconcile two unknown attempts before any paid call; then resume the same P2 run and ceiling. Budget approval persists; do not create a fresh allowance.
- Owner command: `.venvs/judge/bin/python scripts/annotate.py label`; open the current blind Markdown in an editor for long traces.
- Blockers: two unresolved P2 attempts, human labels, other phase budgets, external submission and final-claim approval. No pro call made.
- Spend: cumulative total UNKNOWN. Known-record conservative subtotal $2.762149; new successful-response subtotal $0.061470. Estimated unresolved reserve $0.011710 is not actual usage and has not unblocked the guard.
- Balance: 2026-11-06 post-run CNY 10.41 (pre-run 10.60); no per-request invoice. Full stopped checkpoint: APPROVED_RUNS.md.
- Preservation: full backup `../my-project-backup-20261105-091258`; inherited edits committed as `10abb5e`.
- Working tree: code, tests and delivery docs committed at handover; raw artifacts and owner labels remain ignored local assets, untouched by the agent after blank-kit creation.

## Checkpoints

1. Recovery: inspected Git, processes/containers, histories, recent mtimes, all source modules and existing tests; no labels existed. Details in `STATE_RECOVERY.md`.
2. Scope: user explicitly requests autonomous free development after recovery; no extra design approval or new worktree is needed for local project fixes. Upstream checkouts remain read-only.
3. Annotation: full generated text, exclusive template creation, atomic label saves,
   duplicate validation, private fresh repeat ids with two-day wait. Frozen selection
   50/87 (44 framework pass/6 fail; off27/on23); raw source hashes retained locally.
4. Judge: exclusive run lock, manifest identity includes model/base URL/input hash/
   full config/upstream hash; atomic row checkpoints reconstruct projection, skip
   successful jobs, reject duplicate jobs and legacy unverified outputs. Stale lock
   after process death requires process inspection before removal. Comprehensive
   output must cover all tool batches exactly once; swallowed budget errors propagate.
5. Offline analysis/driver: task-cluster bootstrap; paired repeat/variant joins;
   phase2/3/4 Make targets return pending when no evidence. Canonical experiment.py
   defaults to estimates, --offline forbids endpoint fallback, paid mode needs a
   positive cap and reuses a saved cumulative ceiling (no renewed cap on resume).
6. Free controls: original+8 variants ×50 traces ×2 rules =900 scores. Raw rows at
   outputs/controls/controls-deepseek-flash.jsonl; reports/controls.json derives CIs.
   This is all-selected exploratory rule behavior, not formal human-fail RQ3.
7. Contribution: local isolated clone `.cache/openjudge-contribution`, branch
   fix/trajectory-accuracy-raw-score, commit 8c7490e. Six mock tests pass, with two
   upstream pytest config warnings (pytest-asyncio absent). Portable patch prepared;
   original upstream checkouts untouched. Full upstream unit/quality suites not run.
8. Review: independent reviewer found extra repeats silently truncated and mixed
   model/cap rows hidden by deduplication. Both reproduced as failing tests and
   fixed; added CLI regression for a five-repeat manifest. Report now derives
   repeats and verifies actual job ids against the manifest. Contribution retest
   with an isolated pytest config: 6 passed without warnings.
9. Draft delivery docs: runbook/budgets, incomplete research report, resume evidence,
   Chinese walkthrough and ten interview answers, third-party release boundary,
   local upstream PR draft. No final scientific claim has been approved.
10. Final validation: fresh clone without env/outputs/cache passed 170, using
    existing dependencies and pinned sibling links. Initial setup failure (23
    missing-upstream tests) is disclosed in STATE_RECOVERY. Guarded phase1 replay
    retained the same hash. Actual-key/history scan found no leak; no running
    containers/project workers. Contribution: 12 unit passed, two quality deselected.
