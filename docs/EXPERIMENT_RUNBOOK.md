# Experiment runbook — draft, awaiting owner gates

All commands use `.venvs/judge/bin/python`. Original upstream checkouts are
read-only. No completion in this continuation was sent to DeepSeek. The current
source can plan and replay runs; it cannot manufacture human labels or findings.

## Freeze and annotation

The existing freeze selects 50 trajectories across 36 tasks. Source trace and
sidecar hashes are in `outputs/p2/annotation_set.json`; private strata and cohort
metadata are in `outputs/p2/annotation_meta.json`. Do not rerun selection/build:
they deliberately refuse to overwrite. Owner labels and private keys must be
backed up together, never committed or published.

```sh
.venvs/judge/bin/python scripts/annotate.py label
.venvs/judge/bin/python scripts/annotate.py check
# >= two days after completing round 1:
.venvs/judge/bin/python scripts/annotate.py relabel --count 10
.venvs/judge/bin/python scripts/annotate.py label --round 2
```

No scores/official labels are rendered. Source conversation text is preserved;
incidental model mentions in the original conversation cannot be guaranteed
absent. Do not open the mapping, metadata, scores or past labels during labeling.
Open a blind Markdown file in an editor when terminal scrollback is insufficient.
Blank rows remain unfinished, not implicitly failures. For an undecidable trace,
skip and discuss exclusion policy after the blind round; no automatic label is
assigned. P4 defaults to requiring zero blank round-1 labels. For the current
48-label analysis, pass `--expected-unlabeled 2` to both the run and report
commands. The flag checks the exact count. Eligibility comes from the owner's
failure labels.

## Safe planning and offline reports

```sh
.venvs/judge/bin/python scripts/experiment.py p2
.venvs/judge/bin/python scripts/experiment.py probe
.venvs/judge/bin/python scripts/experiment.py p3 --thinking both --limit 10 --grid-traces 0
.venvs/judge/bin/python scripts/experiment.py p3 --thinking both
make phase2 phase3 phase4
make rule-controls
```

Plans never call a model. `phase2/3/4` only read local evidence and write numeric
reports. `pending` is a valid, explicit absence of results, not stage completion.
`rule-controls` is free and resumable. Its all-selected cohort is exploratory and
must not be presented as formal failed-trajectory RQ3.

`--offline` on `experiment.py` replays exact saved model requests and refuses a
cache miss. Preserve the exact model/thinking/repeat/grid/limit/run-id arguments.
It cannot reproduce a live run that has never occurred. Offline commands can add
cache-hit ledger records and error/null rows; they do not add paid cost.

## Budget plan and approval status

Update 2026-11-07: the owner approved P2 $0.80 and probe $0.20; execution is in
`APPROVED_RUNS.md`. Other rows remain proposals. P2 completed 100/100; probe has
18 observations, 15 valid/3 preserved errors, 17 new calls and one P2 cache reuse.
Do not restart paid jobs to make invalid rows pass. Original manifests/caches
reproduce the same outcomes offline.

Unknown actual usage stays unknown. Budget-only reservations use request byte
bounds and output caps, not measured tokens or exact charges. Overlays fingerprint
original records without rewriting them; unmatched evidence still blocks work.

Measured planning inputs are the complete frozen messages; input tokens use a
character approximation plus prompt overhead and outputs use configured caps.
Peak/cache-miss prices are conservative relative to time/cache discounts, but
the character approximation is not a proven token upper bound. Retry reserve is
not included below. Actual per-request guards still stop an unaffordable call.

| Stage / exact planning configuration | Calls | Peak estimate USD | Proposed next decision |
| --- | ---: | ---: | --- |
| P2 main Direct/off, 50 traces ×2 graders | 100 | 0.630398 | Owner may approve $0.80 cap, off-peak |
| Sampling probe, one frozen trace, on/off ×3 temperatures ×3 repeats | 18 | 0.144169 | Owner may approve $0.20 cap, off-peak |
| P3 flash pilot, 10 traces, Direct, on/off ×3 repeats ×2 graders | 120 | 0.934081 | Review probe and pilot budget before executing |
| P3 full flash grid, 50 traces, 10 grid traces, on/off | 1,320 | 10.124154 | Do not use old $4 proposal as approval; reduce after pilot |
| P3 pro pilot, same 10-trace Direct design | 120 | 3.623352 | Defer until flash pilot and explicit pro budget |
| P4 | Unknown until owner failure labels | Not estimated yet | Estimate actual eligible lengths and count before approval |

No more agent trajectory generation is needed to meet the requested count.
If expansion is later desired, propose a separate fixed-cap cohort with task ×
trial ×agent model/thinking configuration and calibrate cost before collection.
Do not rerun the inherited paid chain scripts. Their numeric caps are not approval.

After explicit owner approval, a live invocation adds `--run --cap-usd <approved>`
and a unique `--run-id`. The driver saves the original absolute ceiling in
`runs/<id>/budget.json`; resume uses that ceiling, not a fresh allowance. A changed
job plan/model/input/cap requires a new run identity and new approval, never an
overwrite. Keep one paid process per shared ledger. Workers share one locked
client; separate clients/processes do not share an in-flight budget reservation.
Run off-peak (weekdays outside UTC 01–04 and 06–10; weekends/Chinese public holidays
are off-peak). No scheduler or background runner has been installed.

For models: read-only `/models` verified flash/pro on 2026-11-05; verify again
before a later paid batch. Flash/pro prices are in `configs/pricing_p3.yaml` from
the [official page](https://api-docs.deepseek.com/quick_start/pricing/). Default
thinking is on except the D24 pre-registered P2 primary configuration (off).

## P3 follow-up and P4 plans, prepared 2026-11-10

The two P3 batches below were approved and executed on 2026-11-10. Their
results and approved commands are in [the run record](APPROVED_RUNS.md).
P4 has a $22.50 approved cap. The owner authorized launch on 2026-11-10.
See [the current checkpoint](PROGRESS.md) for run state. Recheck the model
and off-peak window before a later resume. Preflight balances are historical
snapshots.

P3 holds the sample fixed at the first four frozen traces by trace ID. Compare
Flash and Pro in Direct mode, and compare Direct, Average and Voting on Flash.
Both graders and both thinking settings use three repeats. With one worker,
the strategies use the same three distinct draws per repeat. Direct uses
the first draw, Average and Voting each use all three. The 48 Flash Direct
draws are already cached from the pilot, including one invalid Comprehensive
response. Preserve that response and count any affected panels as incomplete.
This design measures paired strategy
differences on a small fixed cohort. The output caps still differ by thinking
setting, and strategy differences on Pro are outside this matrix.

P4 uses the 16 owner-labeled failures, with two unlabeled traces excluded.
Run Flash with thinking off, both graders, four templates in both insertion
locations, original and perturbed trajectories, with and without the defense
wrapper, and three repeats. Pair within trajectory, grader, defense setting
and repeat. Report score changes and baseline fail-to-pass flips separately.
The report records the number of eligible paired baseline failures and the
number of those pairs that flipped. An empty denominator yields a null rate.
Matched rule controls are in [the aggregate](../reports/p4-human-fail-rule-controls.json).
They were computed with `injection_report` from the existing 900 rule rows after
filtering to `human_fail_ids(expected_unlabeled=2)`.

| Prepared batch | Logical completions | New requests after local reuse | One-attempt peak guard sum | Proposed cap |
| --- | ---: | ---: | ---: | ---: |
| P3 Flash strategies | 336 | 96 | $1.270343 | $1.35 |
| P3 Pro Direct | 48 | 48 | $2.600176 | $2.65 |
| P4 Flash paired injection and defense | 1,728 | 1,680 | $22.469853 | $22.50 |

The preflight rendered the native grader requests, inspected exact cache keys,
and summed the client's one-attempt reservation formula for unique cache misses.
For Flash ensembles it reused the Direct request body with distinct sub-sample
suffixes, matching the native strategies' identical evaluation arguments.
The guard sums use peak prices and include the conservative input-byte and
output-cap bounds. DeepSeek's off-peak rates are half its peak rates.
Recheck scope, cache state, model availability, price and balance before launch.
The read-only balance snapshot on 2026-11-10 was [balance omitted].

These commands are offline cost plans. After approval, append
`--run --cap-usd <approved cap>` to the exact command for each batch and
run them sequentially in off-peak hours.

```sh
.venvs/judge/bin/python scripts/experiment.py p3 --model deepseek-flash --thinking both --limit 4 --grid-traces 4 --repeats 3 --workers 1 --max-attempts 1 --run-id p3-flash-strategies-4
.venvs/judge/bin/python scripts/experiment.py p3 --model deepseek-v4-pro --thinking both --limit 4 --grid-traces 0 --repeats 3 --workers 1 --max-attempts 1 --run-id p3-pro-direct-4
.venvs/judge/bin/python scripts/experiment.py p4 --model deepseek-flash --thinking off --repeats 3 --expected-unlabeled 2 --workers 1 --max-attempts 1 --run-id p4-flash-human-fail-16
```

After each run, check its manifest against the original plan, replay stored
results offline and preserve errors. Use `scripts/report_experiments.py` with
the stage and `--input` pointing to the exact run JSONL. Pass
`--expected-unlabeled 2` for the P4 report. The offline report command writes
the stage's default JSON filename. Keep each run's report under a distinct name.

To regenerate the report for the named P4 batch from local checkpoints:

```sh
.venvs/judge/bin/python scripts/report_experiments.py p4 \
  --input outputs/p4/p4-flash-human-fail-16.jsonl --expected-unlabeled 2
```

Use the same run ID and $22.50 stage cap when resuming this batch. The original
cumulative ceiling remains in its budget checkpoint.

## Recovery and coverage

Run state consists of `manifest.json` (exact hashed job plan), `rows/<job_id>.json`
(atomic authoritative results), and a reconstructable output JSONL. Cache keys
include repeat ids, with distinct per-evaluation suffixes for Average/Voting.
Existing successful jobs are skipped; error jobs replay their existing completion
cache. A cached invalid completion will remain invalid; obtain a new sample only
under a new approved repeat identity, retaining the failure in the audit record.

An interrupted `active.lock` intentionally prevents automatic resumption: inspect
processes first, retain the lock as evidence if needed, then remove only a known
stale lock. Never delete cache/ledger/rows to make a batch start again. Rebuild
JSONL from atomic rows rather than editing truncated evidence by hand.

Reports derive repeat count from the manifest and validate planned job ids.
Incomplete repeat panels, absent baselines and errors are explicit coverage
counts. Confidence intervals use 2,000 seeded task-cluster bootstrap resamples;
undefined kappa/rank draws are omitted, with null CIs when fewer than half are
defined. One cluster gives a degenerate interval, not strong evidence. RQ1
majority-class baseline is fitted on the reported labels and is descriptive.
The random fair-coin baseline is its exact expected accuracy, 0.5.

## Research gates still open

The two blank annotations and delayed re-labeling remain unresolved. The P2
comparison, Flash Direct pilot, and four-trace Flash/Pro and strategy results
are available. The final claims depend on P4 coverage and owner review.
Cross-vendor validation would relax the DeepSeek-only scope and requires
separate approval and credentials. The local OpenJudge proposal awaits
authorization to submit upstream.
