# Progress

## Execution checkpoint — 2026-11-07 CST

- Current: P2 complete 100/100. Probe stopped at six valid +three invalid responses and one pre-network reservation error; resume unchanged ceiling with one worker/one transport attempt.
- Pre-batch estimates: P2 100 calls / peak $0.630398; probe 18 calls / peak $0.144169. Approval and exact commands: APPROVED_RUNS.md.
- Last result: 173 offline tests pass; unknown actual usage stays unknown, conservative reservations are separate, unchanged ceilings still enforced. Earlier clone test: 170; contribution: 12 unit passed.
- Next owner action: label 50 blind traces. Other P3/P4 and external-action budgets remain unapproved.
- Next agent action: experiment.py probe --run --cap-usd 0.20 --workers 1 --max-attempts 1 --run-id probe-deepseek-flash. Keep existing $3.221982 ceiling, preserve format errors, then offline replay/report.
- Owner command: `.venvs/judge/bin/python scripts/annotate.py label`; open the current blind Markdown in an editor for long traces.
- Blockers: human labels, other phase budgets, external submission and final-claim approval. Original actual usage of two attempts remains unknown; evidence-backed budget reservations allow bounded continuation.
- Spend: actual cumulative accounting UNKNOWN (two original attempts). Reservation-inclusive conservative budget cost $3.021982 after P2; P2 increment approximately $0.321302/$0.80. No new unknown attempts during resume.
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
