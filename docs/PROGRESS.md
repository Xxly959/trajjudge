# Progress

## Handover — 2026-11-05 CST

- Current: judge resume/validation fixes implemented; verifying milestone.
- Last result: six failing judge regressions now pass; model/input/cap drift rejected before requests; corrupt JSONL reconstructs from atomic rows.
- Next: offline P2/P3/P4 report drivers and free P4 rule controls; no paid runs.
- Owner command: `.venvs/judge/bin/python scripts/annotate.py label`; open the current blind Markdown in an editor for long traces.
- Blockers: human labels, new phase budgets, pro pricing, external submission authorization; no research conclusions yet.
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
