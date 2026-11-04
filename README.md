# trajjudge

Reliability and prompt-injection audit of LLM graders on agent trajectories.

**Status: phase 1, stage S1 (skeleton).** Stages S2–S7 land incrementally; see
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
make smoke              # available after S2; currently the script is not implemented
```

Model identifiers are **not** hardcoded. `configs/deepseek.yaml` ships with `null`
model ids on purpose: run `make smoke`, which lists the models the endpoint actually
serves, then copy the exact ids into the config.

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
