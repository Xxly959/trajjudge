# Progress

## Handover — 2026-11-05 CST

- Current: offline stage drivers and free P4 rule controls implemented; review underway.
- Last result: 900 free rule evaluations; loop changes 0/400, information-gain changes 177/400. P2/P3/P4 reports explicitly pending.
- Next: verify review fixes and delivery docs, fresh source-clone tests, final evidence checks.
- Owner command: `.venvs/judge/bin/python scripts/annotate.py label`; open the current blind Markdown in an editor for long traces.
- Blockers: human labels, new phase budgets, external submission and final-claim approval. Pro pricing verified in separate pricing_p3.yaml; no pro call made.
- Spend: conservative cumulative $2.700680 (P2 $2.681012; phase1 $0.019668), includes one estimated unknown call; new paid spend $0.
- Balance: read-only API CNY 10.74; no opening balance/invoice, cannot fully reconcile.
- Preservation: full backup `../my-project-backup-20261105-091258`; inherited edits committed as `10abb5e`.
- Uncommitted: annotation safety code/tests/guide and this checkpoint, committed together immediately after suite verification.

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
