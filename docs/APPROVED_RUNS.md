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
