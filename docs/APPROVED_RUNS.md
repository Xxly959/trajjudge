# Approved execution checkpoints

## 2026-11-06: P2 main judge and sampling probe

Owner replied “批准” to the explicit proposal: P2 **USD 0.80** and sampling
probe **USD 0.20**, both off-peak. This authorizes these two existing plans only,
not P3 full/pilot/pro runs, P4, external submission or final resume claims.

Preflight at 2026-11-06 14:42 UTC (22:42 CST), an off-peak time:

- Clean project worktree; no existing P2/probe run directories or live runner.
- `/models`: `deepseek-flash`, `deepseek-v4-pro`; only flash will be called.
- Official price page rechecked: flash peak/cache-miss input/output USD 0.30/1.20
  per million; off-peak 0.15/0.60. Keep conservative peak accounting.
- Conservative starting cumulative cost **USD 2.700680**; 960 ledger records,
  80 cached, unchanged billable tokens since recovery.
- Read-only balance **[balance omitted]** (previous snapshot [balance omitted]). The difference
  is not explained by this unchanged project ledger; do not attribute it to a
  project run or infer an exchange rate/invoice.
- Frozen trace hashes verified by both plan commands; owner labels untouched.

| Run id | Planned jobs/calls | Peak planning estimate USD | Approved cap USD |
| --- | ---: | ---: | ---: |
| p2-deepseek-flash | 100 / 100 | 0.630398 | 0.80 |
| probe-deepseek-flash | 18 / 18 | 0.144169 | 0.20 |

P2: 50 traces × Accuracy/Comprehensive, Direct, thinking off, repeat 0 (D24).
Probe: one fixed frozen trace × thinking on/off × temperature default/0/1.5 ×
three repeats, Accuracy only. Output diversity is descriptive, not proof of
server-side sampling semantics. Input estimates are character approximations;
output uses configured caps and retries are guarded separately by the client.

Run serially by phase, with at most two worker threads sharing one client and
ledger. Save each original ceiling in `runs/<id>/budget.json`; never renew the
cap on resume. Total new authorized spend cannot exceed USD 1.00. Stop at a
guard failure or excessive cost; do not weaken validation or fabricate scores.

Commands:

```sh
.venvs/judge/bin/python scripts/experiment.py p2 --run --cap-usd 0.80 --workers 2 --run-id p2-deepseek-flash
.venvs/judge/bin/python scripts/experiment.py probe --run --cap-usd 0.20 --workers 2 --run-id probe-deepseek-flash
```

Results and after-run reconciliation will be appended before handover. Raw
requests/responses and per-trace scores remain ignored local evidence; no scores
are shown in the blind annotation interface.

### P2 stopped checkpoint, 2026-11-06 14:45 UTC

Runner exit 1: 20/100 successful jobs, 21 result rows (one explicit error),
`stopped_early=1`. The ledger has 20 successful completions and two additional
unknown attempts, followed by successful retries. Original usage is unavailable;
no ledger row was rewritten and no unknown attempt was treated as free.

- Known-response stage usage: 180,465 input / 6,108 output tokens; conservative
  peak-price subtotal **USD 0.061470**, excluding both unresolved attempts.
- Overall known-record subtotal **USD 2.762149**. The client total remains
  **UNKNOWN**, not this subtotal.
- Planning reserve for unresolved attempts: approximately **USD 0.011710**,
  using same-tag successful-retry input tokens plus configured output caps
  (Accuracy 1,024; Comprehensive 3,072), at peak/cache-miss prices. Combined
  subtotal plus estimated reserve: USD 2.773859. This is not actual recovered
  usage or a reason to bypass the guard.
- Read-only post-run balance **[balance omitted]**; no per-request charge reconciliation.
- No live runner remains. Probe was not started; both original approvals remain
  valid. Never reset the original P2 ceiling or add a fresh allowance on resume.

Preserved: `runs/p2-deepseek-flash/{budget.json,manifest.json,rows/}`,
`outputs/p2/p2-deepseek-flash.jsonl`, usage/cache, and
`outputs/verification/p2-20261106-live.log`. Before another paid request, reconcile
the unknown usage or document a conservative reservation without calling it
actual usage; preserve originals. Formal RQ1 still needs owner labels.

### 2026-11-07 continuation preparation

Owner requested continuation; existing caps remain approved. Saturday is
off-peak throughout the day; models, flash prices and [balance omitted] balance were
rechecked before paid execution. No new spend during repair.

Implemented separate conservative budget accounting while original unknown usage
remains unknown. Offline exact-request reconstruction gives input byte bounds
38,246 / 51,737 and output caps 3,072 / 1,024, more conservative than the previous
retry-token-only planning reserve. Reservation-inclusive cumulative guard amount
is **$2.794060**, below unchanged P2 ceiling **$3.500680**.

`scripts/reserve_unknown.py --apply` preserves all original ledger entries,
stores audit evidence under `runs/p2-deepseek-flash/accounting/` and overlay at
`outputs/usage/usage.reservations.json`. Planning/reconstruction uses cache only;
it appends cache-hit records but never sends a model request. It does not recover
the provider's actual usage. New transport errors record the same request bound
directly as budget-only metadata; absent evidence still blocks paid calls.

Independent review found no blocking defect. Full offline suite: 173 passed.
Resume exact original P2 manifest/ceiling and cached successes, then run the
approved 18-call probe. Other P3/P4/pro runs remain unapproved.

### P2 complete; probe pre-batch checkpoint (2026-11-07)

P2 runner returned exit 0: 80 jobs run, 20 skipped from original successes,
zero errors, no early stop. Authoritative manifest has **100/100 ok**. No new
unknown attempt arose during continuation; original two remain unknown with
separate reservations. Cumulative conservative budget accounting: **$3.021982**,
below unchanged P2 ceiling $3.500680. Increment relative to original $2.700680
starting guard amount is approximately **$0.321302**, below approved $0.80.

Before probe: same frozen plan, **18 calls**, peak planning estimate **$0.144169**,
approved cap **$0.20**, no existing probe budget/manifest. New probe ceiling will
be $3.221982 (current reservation-inclusive guard amount plus its separate cap).
Saturday remains off-peak. Use `probe-deepseek-flash`, two worker threads, and
never enlarge the allowance on resume. Human labels and RQ1 conclusions remain pending.

### Probe reservation stop and safer operational retry policy

First probe invocation: nine response observations (eight new API calls and one
P2 cache reuse); six valid grades and
three invalid high-temperature outputs (thinking off, temperature 1.5). One
thinking-on job was blocked before network by the worst-case retry reservation;
runner exit 1, 10 attempted result rows, stopped_early=1. The three invalid
responses stay errors, not repaired scores. Successful-response cost subtotal
was $0.030854, well below the approved $0.20, and no unknown attempt was added.

Resume the exact manifest and saved $3.221982 ceiling with **one worker and one
transport attempt per completion**. This reduces maximum simultaneous/retry
liability without changing model prompts, temperature, caps, repeats or budget.
Already cached invalid completions are revalidated without paying again; do not
try a new model sample to hide their format failures. New transport failures will
still stop the runner and record conservative bounds. The new max-attempts CLI
option is unit tested to preserve the original approved cap.

### Completed approved execution (2026-11-07)

| Run | Original observations | Valid / error | New completion responses | Conservative run budget cost USD | Cap USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| P2 main | 100 | 100 / 0 | 100, plus two original unknown attempts | 0.321302 including unknown reservations | 0.80 |
| Probe | 18 | 15 / 3 | 17, plus one reused P2 cache entry | 0.065370 | 0.20 |

Probe continuation returned exit 1 because three genuine invalid outputs remain
errors; stopped_early=0 and all 18 planned rows are present. Errors are thinking-off,
temperature 1.5: one length cap and two missing-schema-field outputs. Other five
groups have 3/3 valid scores. No parameter-rejection HTTP result was observed.
No output was repaired or resampled to hide failures.

Valid scores happen to be 3 throughout this one-case probe. This does not prove
temperature is ignored or honored, or establish judge stability. Thinking-off/on
caps differ (1,024 /4,096); off/default/repeat-0 is an earlier P2 sample, not a
fresh probe call. Preserve that cross-phase reuse in later analysis.

Cache replays: P2 **100 cached, 0 API**; probe **18 cached, 0 API**. Every job's
score/status/model/thinking/temperature/cap/repeat matched, including errors.
Replay exits P2=0, probe=1 (expected error preservation). Use `--offline` with
separate `*-replay` run ids.

Combined approved-run conservative budget cost **$0.386672 / $1.00**. Cumulative
reservation-inclusive guard amount **$3.087352**; ledger subtotal excluding the
two new unknown attempts **$3.055441** (still includes the older recorded
reconciliation estimate). Actual cumulative accounting stays UNKNOWN for two original
attempts, separately reserved. Post-run balance **[balance omitted]**; no exact invoice or
currency reconciliation claimed. No pro/P3 full/P4 calls, external writes or
owner-label edits were performed.

## 2026-11-09: P3 Flash Direct pilot

The owner approved the proposed pilot in chat with a **$1.50** new-spend cap.
The pilot uses the first ten frozen traces by trace ID, both LLM graders, both
thinking modes and three Direct repeats. The pre-batch request audit found 25
reusable completions (20 P2, five probe) and 95 distinct new requests. The new
requests were estimated at $0.380543 off-peak, $0.761087 at peak, or $1.429950
using the summed conservative peak request bounds. Model listing confirmed
`deepseek-flash` before the off-peak launch.

```bash
.venvs/judge/bin/python scripts/experiment.py p3 --model deepseek-flash --thinking both --limit 10 --grid-traces 0 --repeats 3 --workers 2 --max-attempts 1 --run-id p3-flash-direct-pilot --run --cap-usd 1.50
```

The command saved 120/120 planned rows, 119 valid and one error. The
thinking-on Comprehensive completion failed raw validation because its step
evaluations did not cover each assistant tool batch exactly once. Exit 1
records that error. The runner did not stop early. A separate offline replay
with a temporary ledger matched status, score and reason for all 120 jobs
from cache, including the invalid completion, with zero API requests.

- Raw results: `outputs/p3/p3-flash-direct-pilot.jsonl`, SHA-256
  `b59114369f67dc12d0483c35788a69911af1eb54a4b89a88c10cee3d5a7967f5`.
- Run manifest, original ceiling and atomic rows: `runs/p3-flash-direct-pilot/`.
- Numeric report and task-cluster intervals: [p3-flash-direct-pilot.json](../reports/p3-flash-direct-pilot.json).
  Regenerate the analysis locally with
  `.venvs/judge/bin/python scripts/report_experiments.py p3 --input outputs/p3/p3-flash-direct-pilot.jsonl`
  (writes the default `reports/p3.json`).
- Usage: 95 new completions, 845,353 input tokens and 73,978 output tokens;
  25 cache reuses. Conservative cost $0.342380 / $1.50, with no new unknown
  attempt and no pending accounting marker. Cumulative guard accounting
  $3.429732 includes historical reservations. Post-run balance [balance omitted] is
  a separate read-only snapshot.

## 2026-11-10 P3 matched Flash strategies and Pro Direct

The owner approved the two prepared P3 batches with separate caps of $1.35
for Flash and $2.65 for Pro. Both ran in the midday CST off-peak window
with one worker and one attempt per request. The batches used the first four
frozen traces by trace ID, two graders, both thinking modes and three repeats.
Flash Direct uses the first draw per repeat. Average and Voting share the
three draws. The same four traces and Direct configuration are used for Pro.

```sh
.venvs/judge/bin/python scripts/experiment.py p3 --model deepseek-flash --thinking both --limit 4 --grid-traces 4 --repeats 3 --workers 1 --max-attempts 1 --run-id p3-flash-strategies-4 --run --cap-usd 1.35
.venvs/judge/bin/python scripts/experiment.py p3 --model deepseek-v4-pro --thinking both --limit 4 --grid-traces 0 --repeats 3 --workers 1 --max-attempts 1 --run-id p3-pro-direct-4 --run --cap-usd 2.65
```

| Run | Planned rows | Valid / error | New completions | Local cache reads | Guard cost / cap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Flash strategies | 144 | 139 / 5 | 96 | 240 | $0.274548 / $1.35 |
| Pro Direct | 48 | 46 / 2 | 48 | 0 | $0.627312 / $2.65 |

Flash had three affected rows from the shared step-coverage error and two
rows affected by an invalid JSON payload. Pro had two thinking-on Comprehensive
responses hit the 4,096-token output cap. Both commands exited 1 to report
these errors and neither stopped early. An isolated cache replay matched
all 192 stored statuses, scores and reasons, including errors, with zero API calls.

- Flash source `outputs/p3/p3-flash-strategies-4.jsonl`, SHA-256
  `5100ee612542a379faf494b0ec178bd5c7ab8cd6c564d629c684d6664dc847f0`.
  [Aggregate report](../reports/p3-flash-strategies-4.json).
- Pro source `outputs/p3/p3-pro-direct-4.jsonl`, SHA-256
  `288c21d3cf377b2edcfa21be6f745b39b01fe1fe3bc85b0705d41bf2e55a9e5d`.
  [Aggregate report](../reports/p3-pro-direct-4.json).
- Manifests and budgets are in the corresponding `runs/<run-id>/` directories.
  Regenerate each aggregate with `scripts/report_experiments.py p3 --input <run JSONL>`.
  Compare Direct rows with matching trace, grader, thinking mode and repeat
  after filtering to valid rows. The report's `phase_usage` is cumulative P3
  usage at generation time, while `latest_row_usage` is scoped to that run.
- Balance snapshots before Flash, after Flash and after Pro were recorded locally. The two batches added $0.901859 to the guard ledger,
  which totals $4.331591 including historical reservations. The two rounded
  per-batch costs differ from the combined ledger delta by $0.000001.

## P4 Flash paired perturbations — 2026-11-10 CST

The owner authorized the full run against 16 owner-labeled failures, excluding
two blanks. DeepSeek Flash availability and off-peak pricing were confirmed.
The original $22.50 guard cap was preserved.

```sh
.venvs/judge/bin/python scripts/experiment.py p4 --model deepseek-flash --thinking off --repeats 3 --expected-unlabeled 2 --workers 1 --max-attempts 1 --run-id p4-flash-human-fail-16 --run --cap-usd 22.50
.venvs/judge/bin/python scripts/report_experiments.py p4 --input outputs/p4/p4-flash-human-fail-16.jsonl --expected-unlabeled 2
```

- 1,728/1,728 rows, 1,701 valid and 27 errors. The errors were all in
  Comprehensive: 15 missing step evaluations, four incomplete step-coverage
  results, and eight invalid JSON responses. Exit 1 reflects these errors.
  No early stop or uncertain attempt occurred.
- 1,496/1,536 valid original–perturbation pairs. [Aggregate](../reports/p4.json)
  carries variant-level intervals and fail-to-pass denominators. It marks
  valid coverage partial and retains the error count.
- A fresh isolated `--offline` run with copied inputs and cache and sockets
  blocked reproduced all 1,728 job IDs, statuses, scores and reasons. It also
  exited 1 because it reproduced the same errors. The live ledger stayed intact.
- 1,680 new completions and 48 local cache hits. New usage includes 13,361,646
  provider cache-hit input tokens, 766,958 cache-miss input tokens and 508,592
  output tokens. Published off-peak pricing yields an estimated $0.460284.
  The conservative guard added $4.848892, for $9.180483 cumulative including
  the previous reservations. No invoice was reconciled.
- Source JSONL SHA-256
  `10a0e5a3156c846fd07f9ea9a7473b3445e8b354b41234110a521009f7ba8f0a`.
  Manifest SHA-256
  `6d90c46494e8f5c3676c4e70a8601c48c07dc6fcad9fd1fe1ba766b3bd4c8f50`.
  The local budget checkpoint preserves the original $26.831591 absolute ceiling.
