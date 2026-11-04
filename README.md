# trajjudge

Reliability and prompt-injection audit of LLM graders on agent trajectories.

**Status: phase 1, S1–S2 complete (skeleton and DeepSeek smoke probe).** S3–S7 land incrementally; see
`notes/log.md` for the per-stage record and `docs/DECISIONS.md` for rationale.

## What this project studies

Given agent trajectories produced by [Claw-Eval](../claw-eval), how trustworthy are
the verdicts of [OpenJudge](../OpenJudge) graders that are supposed to score them?

Three research questions drive phase 1:

1. **Agreement** — how closely do LLM trajectory graders track the benchmark's own
   scores (and, in phase 2, human labels)?
2. **Stability** — does the same grader return the same verdict on repeated runs?
3. **Robustness to injection** — do instructions embedded in tool output or task
   fixtures move the score?

Phase 1 only connects the pipeline end to end and publishes a v0 report; stability
and injection experiments are phase 2.

## Layout

```
src/trajjudge/     config, unified LLM client (cache + retries + usage), adapter, runner
configs/           DeepSeek endpoint, pricing table, (later) Claw-Eval overrides
scripts/           smoke probe, phase-1 entry point, report generator
tests/             offline suite; every LLM call is mocked
samples/           small fixtures such as the OpenJudge weather trajectory
data/              local, git-ignored working data
notes/log.md       per-stage command log (Chinese)
docs/DECISIONS.md  design decisions and their rationale
```

## Quickstart

```bash
make install            # creates .venvs/judge (Python 3.12) and installs this package
cp .env.example .env    # then put the real DeepSeek key in .env
make test               # offline
make smoke              # bounded DeepSeek probe; uses cached responses when present
make smoke SMOKE_ARGS=--offline  # replay the complete probe without network access
```

The selected model is `deepseek-flash`, confirmed by the endpoint's model list
on 2026-11-04. Both configured roles use that ID following the user's selection.
Model IDs live in `configs/deepseek.yaml`, not in Python code. To inspect the
cached model list or estimate the probe before paid completions:

```bash
.venvs/judge/bin/python scripts/smoke_llm.py --list-models
.venvs/judge/bin/python scripts/smoke_llm.py --estimate
```

The probe runs five completions: plain chat, thinking off, thinking on, a local
tool request in thinking mode, and a follow-up carrying the unchanged assistant
`reasoning_content`. Thinking probes use `reasoning_effort="low"`; this is an
explicit cost choice, different from the provider's default high effort.
The tool is a deterministic local fixture, not a real weather/search service.
Only reasoning presence is printed; reasoning text stays in the ignored cache.

Each run prints usage and appends its summary to `notes/log.md`. Local evidence
is saved as `outputs/smoke/s2.json` (online) and `s2-offline.json` (cache replay).
Model discovery also uses the shared cache, retry policy and usage log; its
metadata requests consume zero model tokens and are excluded from costs.
`--offline` forbids SDK requests and does not require a key. A cache miss fails.
Caches and usage logs are local ignored data; another clone needs to populate
or obtain these caches before offline replay.

Prices were checked against the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/)
on 2026-11-04. Reports and budget checks use peak input cache-miss/output prices
($0.30/$1.20 per million tokens), even during off-peak hours or prompt-cache hits.
The probe has an additional $0.05 reservation within the cumulative $3 budget.
This is a conservative estimate, not the provider's invoice.

## Constraints

- One provider only (DeepSeek). Cross-provider claims are out of scope for phase 1.
- No upstream forks: `../claw-eval` and `../OpenJudge` are read-only dependencies.
- Costs are tracked per call in `outputs/usage/usage.jsonl`; the phase-1 budget is
  roughly USD 3.


## S1 safeguards and current limits

Python 3.11–3.12 is supported; `make install` selects Python 3.12 and uses uv
for the isolated editable installation. The uv cache defaults to `.cache/uv`;
set `UV_CACHE_DIR` to override it. Judge and Claw-Eval environments stay separate.
No runtime dependency was added by the S1 repair.

Every completion checks the disk cache first, including calls with the legacy
`use_cache=False` argument. Cache format v2 includes the endpoint and all request
parameters. Existing v1 cache files are not reused. Cache hits need no pricing
lookup or SDK creation. S6/S7 will add the complete offline report pipeline;
`make phase1` remains a stage placeholder today.

Before a paid completion, the client requires verified model prices and checks
the cumulative USD 3 budget. It reserves all configured attempts using a
conservative estimate (serialized UTF-8 request bytes plus 4,096 input tokens,
and `max_tokens`, default 1,024, for output). This is an engineering estimate,
not a provider billing guarantee. Execution must be serial; parallel processes
must not share this budget ledger. Batch estimates will still be presented for
approval at the relevant gate. SDK retries are disabled; the wrapper owns retries.

Usage is logged before response parsing or cache writes. Raw provider usage is
preserved, including cache/reasoning details when present. Input cost currently
uses the configured input price for all input tokens, a conservative estimate
when the provider discounts prompt-cache hits. It is not an exact invoice.
Failed attempts are recorded separately. Unknown billing, a corrupt ledger, or
a `.pending` accounting marker blocks new paid completions; reconcile with the
provider before resuming, rather than deleting records to bypass the guard.
Cache hits remain available. A full disk cannot guarantee a usage-log write;
the pending marker prevents silently continuing after that failure.

`make test` blocks network connections and mocks all LLM responses. `make secrets`
checks both staged blobs and nonignored working files, including `.env.example`.
Run it immediately before every commit. Checks report paths only, never values.
