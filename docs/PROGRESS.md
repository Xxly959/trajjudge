# Progress

## P4 paused before launch — offline rehearsal, 2026-11-10 CST

- The owner deferred API calls. The previously approved P4 cap is $22.50. Wait for the owner's request to resume, then recheck balance, model and off-peak time.
- A socket-denied rehearsal used synthetic scores for the full 1,728-job plan. The report matched all job IDs and formed 1,536 perturbation pairs across 16 eligible traces. The rehearsal wrote to a temporary directory and preserved the live ledger and labels.
- The P4 report marks a run complete only when the manifest identities match, all planned rows are valid, each eligible trace has perturbation results and every reported pair has its baseline. Missing pairs and rows retain explicit partial statuses.
- Verification: 180 offline tests passed. The OpenJudge patch and draft remain ready for separate submission approval. The walkthrough now includes a short interview explanation using verified P2 and P3 results.

## Approved P4 run — waiting for off-peak, 2026-11-10 CST

- Owner confirmed the previously proposed $22.50 stage cap in chat. The run remains scoped to 16 owner-labeled failures, with two blank records excluded, 1,728 planned jobs and 48 reusable results.
- Read-only available balance increased to [balance omitted]. Starting guard accounting is $4.331591 with no pending marker. The run ID is free. The provider may stop requests if the account balance is exhausted.
- The weekday peak window started at 14:00 CST. Recheck balance, pricing and model availability before the 18:00 CST off-peak launch. Use the exact P4 command in the runbook with `--run --cap-usd 22.50`.

## P4 preflight — 2026-11-10 CST

- The plan verifies 16 human-fail trajectories and two unlabeled records. There are 1,728 logical completions, including 192 original-baseline slots. An offline replay found 48 reusable valid original results. No P4 completion requests were sent.
- Of the reusable undefended baselines, Accuracy judged three of 24 as fail and Comprehensive judged all 24 as pass. The report now exposes the fail-to-pass count and its eligible baseline-failure denominator. A zero denominator yields a null rate. Both rule reports were regenerated.
- Using the 32 first-repeat baselines as a token proxy, the estimated 1,680 new requests cost about CNY 16.31 at off-peak cache-miss prices, of which CNY 2.24 is output. Perturbations, caching and actual completion length can change the charge. The proposed stage guard remains $22.50.
- Current balance snapshot: [balance omitted], with no pending accounting marker. P4 awaits sufficient balance and explicit approval of the stage cap. The funded run uses the exact P4 command in `docs/EXPERIMENT_RUNBOOK.md`. The project passed 177 offline tests.

## P3 follow-up verified — 2026-11-10 CST

- Flash strategy comparison: 144 rows, 139 valid and five errors. Pro Direct: 48 rows, 46 valid and two length-limit errors. The 192 rows replayed from cache with zero API calls.
- On four matched traces, Flash Accuracy voting and Pro Direct Accuracy each had 1/4 complete panels flip with thinking off. Flash and Pro Direct disagreed on 1/45 valid paired verdicts. All valid Comprehensive verdicts passed in both runs.
- 144 new requests and 240 local cache reads. New conservative guard cost $0.901859 / $4.00, cumulative $4.331591 including historical reservations. Post-run balance [balance omitted]. No active runner or pending accounting marker.
- Reports: `reports/p3-flash-strategies-4.json` and `reports/p3-pro-direct-4.json`. Exact scope, commands and raw evidence hashes are in `docs/APPROVED_RUNS.md`.
- Next: P4 LLM experiment on the 16 human failures needs its own budget and available balance. The OpenJudge patch and draft await owner approval for external submission.

## P3 Flash verified and Pro pre-batch — 2026-11-10 CST

- Flash strategies saved all 144 rows: 139 valid and five invalid. The 336 logical completions used 96 new API responses and 240 local cache reads. Offline replay matched every row from cache, including all errors.
- Flash conservative guard cost: $0.274548 / $1.35. Current guard ledger: $3.704280. No pending accounting marker. The read-only balance after Flash was [balance omitted].
- The approved Pro Direct batch uses the same four traces, both graders and thinking modes, with three repeats. Plan: 48 new requests, peak estimate $1.314720, one-attempt guard sum $2.600176. Stage cap $2.65 and absolute ledger ceiling $6.354280. Still off-peak.
- Next: run the exact Pro command in the runbook, preserve errors and verify both cohorts together.

## Approved P3 follow-up — preflight, 2026-11-10 CST

- Owner approved the proposed two P3 batches in chat. Caps: Flash strategies $1.35 and Pro Direct $2.65. Both model IDs were confirmed through a fresh model-list request.
- Starting guard accounting: $3.429732 with historical reservations and no pending marker. Balance snapshot: [balance omitted]. The Flash and Pro run IDs were free.
- Runbook plans: Flash 336 logical completions with 96 new requests, Pro 48 new requests. One-attempt peak guard sums are $1.270343 and $2.600176. The Flash cache includes one invalid result from the pilot.
- Wait for the off-peak window opening at 12:00 CST. Launch Flash first and verify remaining balance before Pro. The P4 and upstream submission approvals remain separate.

## Local deliverables and remaining runs — 2026-11-10 CST

- `make phase2` generated the aggregate report on 48 human labels. Both judges matched 32/48, equal to always-pass. Two blanks and delayed re-labeling remain outside this result.
- P4 now accepts an explicit exact blank count. With two blanks, the plan uses 16 owner failures. The matched rule report records 0/128 loop changes and 56/128 lexical changes.
- Updated the research report, resume draft and Chinese walkthrough. The OpenJudge patch applies to upstream `eb34c3b94c90`. Its focused offline unit run passed 12 tests with two quality cases deselected.
- Verification: 176 project tests passed locally and in a fresh source clone with pinned sibling links and existing dependencies. `make phase1` reproduced the existing report hash from cache. No new completion calls. Guard accounting remains $3.429732 including historical reservations. Read-only balance snapshot: [balance omitted].
- Next runs and proposed caps: Flash strategies $1.35, Pro Direct $2.65, P4 $22.50. See `docs/EXPERIMENT_RUNBOOK.md` for the exact offline plans and launch steps. Paid runs, upstream submission and public wording await owner approval.

## P3 Flash Direct pilot — results, 2026-11-09 CST

- All 120 planned rows are present: 119 valid and one rejected step-coverage result. The run used 95 new completions and 25 cached results. Offline replay matched all 120, including the error, with zero API calls.
- Across 39 complete three-repeat panels, no pass/fail verdict flipped. Accuracy scores stayed fixed in both thinking modes. Comprehensive scores varied on 8/10 complete panels with thinking off and 8/9 with thinking on; all 59 valid Comprehensive results passed.
- Pilot summary: `reports/p3-flash-direct-pilot.json`. Run details and reproduction command: `docs/APPROVED_RUNS.md`. The paid runner exited with no early stop and its lock is clear.
- Conservative pilot accounting: $0.342380 / $1.50; cumulative guard ledger $3.429732 including historical reservations. Read-only post-run balance was [balance omitted], a balance snapshot with no invoice reconciliation.
- Next: interpret the pilot with the 48-label partial P2 comparison. A wider P3 grid needs a new approved budget; formal P4 still requires an eligible human-fail cohort under the annotation protocol and an approved budget.

## P3 Flash Direct pilot — pre-batch checkpoint, 2026-11-09 CST

- Scope approved in chat: 10 frozen traces, two graders, thinking on/off, three repeats, Direct. Reuse 25 matching cached completions (20 P2, five probe); preflight identified 95 distinct new requests. Zero completion calls in preflight.
- New-spend cap: $1.50. Estimated new completions $0.380543 off-peak or $0.761087 at peak, with $1.429950 summed peak request bounds at one attempt per completion. Starting guard ledger $3.087352, including historical reservations; absolute ceiling $4.587352.
- Live preflight confirmed `deepseek-flash` in a fresh model listing, off-peak time, a free run ID, and no unreconciled pending request. Latest previously recorded balance was [balance omitted] on 2026-11-07.
- Next: launch the approved command below, monitor atomic checkpoints, then report coverage, verdict flips, replay and accounted cost. Formal P3 grid and P4 remain pending. P2 has 48 human labels and a separate partial offline analysis; two records remain unlabeled.

```bash
.venvs/judge/bin/python scripts/experiment.py p3 --model deepseek-flash --thinking both --limit 10 --grid-traces 0 --repeats 3 --workers 2 --max-attempts 1 --run-id p3-flash-direct-pilot --run --cap-usd 1.50
```

## Execution checkpoint — 2026-11-07 CST

- Current: approved execution finished. P2 100/100 valid; probe 18 observations, 15 valid/3 errors, 17 new calls +1 P2 cache reuse. Both cache replays match; no live runner remains.
- Pre-batch estimates: P2 100 calls / peak $0.630398; probe 18 calls / peak $0.144169. Approval and exact commands: APPROVED_RUNS.md.
- Last result: 175 offline tests pass. P2/probe cache replays match all verdicts; historical phase1 replay is byte-identical after fixing offline-vs-later-live-accounting coupling. Earlier clone test: 170; contribution: 12 unit passed.
- Next owner action: label 50 blind traces. Other P3/P4 and external-action budgets remain unapproved.
- Next: owner completes blind annotation; agent then runs make phase2 (offline). P3 full/P4 require new explicit budgets. No additional paid calls are scheduled; current authorized execution is finished.
- Owner command: `.venvs/judge/bin/python scripts/annotate.py label`; open the current blind Markdown in an editor for long traces.
- Blockers: human labels, other phase budgets, external submission and final-claim approval. Original actual usage of two attempts remains unknown; evidence-backed budget reservations allow bounded continuation.
- Spend: actual accounting UNKNOWN for two original attempts. Conservative run costs P2 $0.321302 +probe $0.065370 =$0.386672/$1.00; cumulative with reservations $3.087352. No new unknown attempts during continuation.
- Balance: 2026-11-07 post-run [balance omitted] (prior balance omitted); no per-request invoice. Full record: APPROVED_RUNS.md.
- Preservation: full backup `<local-backup>`; inherited edits committed as `10abb5e`.
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
