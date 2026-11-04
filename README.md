# trajjudge

Reliability and prompt-injection audit of LLM graders on agent trajectories.

**Status: phase 1, S1–S5 complete (integration probes, reconnaissance and a two-task Claw-Eval pilot).** S6–S7 land incrementally; see
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
make install-openjudge  # editable upstream install, with build output kept in this project
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


## OpenJudge weather smoke (S3)

After `make install-openjudge`, run:

```bash
make smoke-openjudge OPENJUDGE_ARGS=--estimate
make smoke-openjudge
make smoke-openjudge OPENJUDGE_ARGS=--offline
```

The fixture in `samples/weather.json` is copied exactly from the
`TrajectoryAccuracyGrader` example in the upstream agent-graders documentation.
`samples/weather-score.json` records the real smoke result, usage, requested
thinking mode, observed request parameters, and upstream commit. An offline
replay writes `outputs/openjudge/weather-score-offline.json`, preserving the
original online evidence. These are toy documentation examples, not human labels
or evidence of judge reliability.

The native `OpenAIChatModel` accepts explicit `api_key`/`base_url` or reads
`OPENAI_API_KEY`/`OPENAI_BASE_URL`. We pass the project settings explicitly;
`extra_body={"thinking": {"type": "disabled"}}` travels through its native chat
method and the OpenAI SDK. Its SDK HTTP transport delegates to the shared
`LLMClient`, so cached and paid OpenJudge calls use the existing accounting,
retry and budget controls. Only serial non-streaming completions are supported;
unknown request parameters fail rather than disappear.

The grader normally asks the SDK for JSON Schema structured output. DeepSeek's
[documented response format](https://api-docs.deepseek.com/api/create-chat-completion/)
is JSON object output. A project-local subclass selects `json_object` and validates
the parsed object against the original upstream callback schema. Prompts, grader
logic and upstream files are preserved; this response-format adaptation is an
explicit runtime difference. No additional live negative Schema request was made.

OpenJudge's declared runtime dependencies include pandas, NumPy, SciPy and
scikit-learn; they are installed only in the judge environment. No training or
development extras are installed. The installer first installs those dependencies,
then builds the editable upstream package alone with metadata/build directories
redirected to `.cache/openjudge-build`. It checks upstream file hashes before and
after installation. `PYTHONDONTWRITEBYTECODE=1` keeps imports from writing bytecode
into the read-only source; Makefile targets export it automatically.


## Claw-Eval reconnaissance (S4)

See [the reconnaissance report](notes/claw_eval_recon.md) for source-backed config,
CLI, sandbox, trace and scoring details. No Claw-Eval tasks or Docker services
were run in S4. The proposed S5 pilot is two general text tasks,
`T010_contact_lookup` and `T002_email_triage`, with one trial and one worker.
Their required local fixtures exist; attachment tasks with missing files were
excluded from this proposal.

Native endpoint configuration supports DeepSeek, but native execution still
needs the project's cache, accounting and budget integration before a paid run.
The report includes command shapes for review, not a ready-to-run paid pipeline.
Agent thinking can be disabled in config; native Claw-Eval judge thinking stays
on under the earlier decision. The proposal requires user confirmation at the
S4 gate, with costs estimated at $0.03–$0.10 and a $0.75 batch reservation within
the overall $3 budget. These are estimates, not measured Claw-Eval results.


## Two-task Claw-Eval pilot (S5)

Use the independent Claw environment and the unmodified upstream source:

```bash
make install-claw
rtk proxy docker build -f ../claw-eval/Dockerfile.agent -t trajjudge-claw-agent:s5 ../claw-eval
make claw-preflight
make claw-pilot
```

The installer reads the upstream host requirements into `.venvs/claw`; it does
not install OpenJudge or build the upstream package. The launcher supplies
read-only source paths so English graders can locate their peer graders.
It safely loads `.env`, validates all model endpoints and the reviewed upstream
commit, checks fixtures/ports, and checks a disposable Docker sandbox.
Only `T010_contact_lookup` and `T002_email_triage` are permitted, one trial each,
with one spawn worker. Existing `outputs/claw_eval/s5/pilot.json` blocks an extra
run or overwrite. The default script invocation prints an estimate only.

Outputs remain local and ignored:

- `outputs/claw_eval/s5/pilot.json`: results, trace paths, image ID, config/pricing
  hashes, upstream commit, cost ledger summary and runtime differences.
- Per-task native `batch_results.json`, `batch_summary.json` and JSONL traces.
- Per-task `s5_sidecar/requests.jsonl`: exact model request bodies, actual trace ID,
  system prompt, mode, response usage and cache status; no authentication headers.

The project-local worker bindings preserve native message conversion, response
parsing, task execution and graders. They route both agent calls and direct
`judge.client` calls through the shared client. Agent thinking is disabled and
output is capped at 1,024 tokens; native judge thinking remains enabled at default
effort, with its 8,192-token cap. A local non-streaming transport and 60-second
network timeout replace upstream streaming/300-second timeout and layered retries.
The shared client permits at most three attempts. Each task has its original
agent turn limit and at most one logical judge request. Input is never truncated;
requests above the conservative 48k input estimate are rejected. This threshold
was raised from the provisional S4 value because the native tool schema alone
made first-request estimates exceed 22k. The $0.75 batch reservation and $3 stage
budget remain in force and may stop a task early.

On a fatal guard or request error, `S5Stop` bypasses upstream broad retry handlers
while context managers clean resources. A stopped trace may be incomplete;
sidecars and the pilot manifest mark that failure rather than manufacture a score.
All runtime differences are recorded. These are DeepSeek re-runs of framework
rubrics in mock environments, not leaderboard-comparable Gemini/Claude results.
No human labels, repeated-trial stability tests or new injection variants were made.

Observed one-run pilot: T010 score 0.8040, T002 score 0.8500. Nine paid completions
used 38,728 input and 2,161 output tokens; the peak-price conservative estimate
is $0.014212. This is connectivity evidence from two tasks, not a reliability
or model-benefit result. See `notes/log.md` for the measured breakdown.
