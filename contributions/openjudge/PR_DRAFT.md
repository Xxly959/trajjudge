# PR Record: preserve trajectory accuracy raw score before bounding

Submitted upstream as **[agentscope-ai/OpenJudge#246](https://github.com/agentscope-ai/OpenJudge/pull/246)** (status: **MERGED** into `agentscope-ai/OpenJudge:main` by `@helloml0326` at `2026-11-18T05:43:48Z`, merge commit `c58d1d6c295ad2b5c164cf8d275519c77a290e5a`; `Pre-commit / run` CI passed).
Pushed branch: `Xxly959:fix/trajectory-accuracy-raw-score` (rebased onto `agentscope-ai/OpenJudge` `main` at `a850e78`, head commit `276e78966869e410586962c0175ab76002f76642`; originally prepared against `7d27246484e91c6ed4a349b6ebe7bd4629d9378f` / `8c7490e`).

## Proposed description

`TrajectoryAccuracyGrader` bounds model scores to 1–3 and currently records that
bounded value as `metadata["raw_score"]`. For example, a mocked model response of
99 returns `score=3` and `raw_score=3`, hiding the original out-of-range value from
downstream audits. Preserve the original model score in `raw_score` while keeping
the returned score, reason and bounding behavior unchanged. Add six offline
regressions covering below-range, in-range, fractional and above-range outputs,
and document the metadata contract beside the existing qwen3-32b example.

This is a reproducible source/mock finding from our integration audit, not an
observed frequency of malformed real-model scores or a demonstrated improvement
in grading quality. Empty-input handling remains a separate question.

## Local validation

The two out-of-range cases failed before the change; all six pass afterward.
Model grading is mocked. A follow-up run with the existing trajectory-accuracy
unit file passed **12 unit tests**, with two quality tests deselected, under
socket denial and without credentials. The declared pytest-asyncio dev plugin
was temporarily installed in the judge environment for that check. No new
grader, prompt, model request or trajectory fixture is introduced. Original
upstream trees remain untouched; paid quality tests were not run.

```sh
PYTHONPATH="$PWD/.cache/openjudge-contribution" .venvs/judge/bin/python -m pytest \
  -c /dev/null -o markers=unit \
  .cache/openjudge-contribution/tests/graders/agent/trajectory/test_trajectory_accuracy_raw_score.py -q
```

## Review and submission checklist

- [x] A portable format-patch is tracked beside this draft.
- [x] Base Apache-2.0 license and original headers retained; added examples are synthetic.
- [x] Existing score semantics retained; raw metadata now preserves the model value.
- [x] Six mock regression cases and grader documentation prepared.
- [x] Owner reviews scope and authorizes external action.
- [x] Submitted upstream PR [agentscope-ai/OpenJudge#246](https://github.com/agentscope-ai/OpenJudge/pull/246) (`head: 276e78966869e410586962c0175ab76002f76642`, CI run `44234549799` awaiting maintainer workflow approval for first-time contributor).
- [x] On 2026-11-10, verified the portable patch applies cleanly to upstream
  `1c0e05a5cff7b1be3e5d5613befeea31ede38858`. The isolated snapshot passed
  12 focused unit tests with two quality tests deselected and sockets blocked.
  The temporary test environment included the upstream pytest-asyncio dependency.
- [x] Relevant existing accuracy and new unit cases: 12 passed, two quality deselected; re-verified 6/6 offline unit tests passing on rebased commit `276e789`.
- [ ] Run wider upstream suite if requested. Discuss quality-test expectations
  for this metadata-only fix; no paid quality run is authorized.
- [x] Pre-commit CI (`ubuntu-latest`) passed (`2m55s`); approved by `@helloml0326` and merged into upstream `main` (`c58d1d6c295ad2b5c164cf8d275519c77a290e5a`).

Restore the branch later by cloning OpenJudge into a separate directory and
applying `0001-preserve-trajectory-accuracy-raw-score.patch` with `git am`. Do not
apply it to the project's pinned runtime checkout. The patch is standard Git
mail format, whose blank context/signature lines contain intentional whitespace.
