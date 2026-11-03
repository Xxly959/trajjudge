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
make smoke              # network: lists models, then runs the thinking probes
```

Model identifiers are **not** hardcoded. `configs/deepseek.yaml` ships with `null`
model ids on purpose: run `make smoke`, which lists the models the endpoint actually
serves, then copy the exact ids into the config.

## Constraints

- One provider only (DeepSeek). Cross-provider claims are out of scope for phase 1.
- No upstream forks: `../claw-eval` and `../OpenJudge` are read-only dependencies.
- Costs are tracked per call in `outputs/usage/usage.jsonl`; the phase-1 budget is
  roughly USD 3.
