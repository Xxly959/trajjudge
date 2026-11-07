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
- Read-only balance **CNY 10.60** (previous snapshot CNY 10.74). The difference
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
- Read-only post-run balance **CNY 10.41**; no per-request charge reconciliation.
- No live runner remains. Probe was not started; both original approvals remain
  valid. Never reset the original P2 ceiling or add a fresh allowance on resume.

Preserved: `runs/p2-deepseek-flash/{budget.json,manifest.json,rows/}`,
`outputs/p2/p2-deepseek-flash.jsonl`, usage/cache, and
`outputs/verification/p2-20261106-live.log`. Before another paid request, reconcile
the unknown usage or document a conservative reservation without calling it
actual usage; preserve originals. Formal RQ1 still needs owner labels.

### 2026-11-07 continuation preparation

Owner requested continuation; existing caps remain approved. Saturday is
off-peak throughout the day; models, flash prices and CNY10.41 balance were
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
attempts, separately reserved. Post-run balance **CNY 9.70**; no exact invoice or
currency reconciliation claimed. No pro/P3 full/P4 calls, external writes or
owner-label edits were performed.
