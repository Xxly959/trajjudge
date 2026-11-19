# PR Record: expose voting tie metadata and document distinct ties

Status: **MERGED into `agentscope-ai/OpenJudge:main`** (PR **[agentscope-ai/OpenJudge#248](https://github.com/agentscope-ai/OpenJudge/pull/248)** approved and merged by `@helloml0326` at `2026-11-18T06:54:45Z`, merge commit `15d22f2ca4e20413bc91f6f52ee65d5bee12b3cd`; `Pre-commit / run (ubuntu-latest)` CI passed; closed Issue [#247](https://github.com/agentscope-ai/OpenJudge/issues/247)).
Pushed branch: `Xxly959:fix/voting-tie-metadata` from `.cache/openjudge-contribution` (based on `agentscope-ai/OpenJudge` `main` at `c58d1d6`, commit `7dc3955297dc9dcaad3248617a8fe2c988b60422`).
Portable patch: [0002-voting-tie-metadata-and-docs.patch](0002-voting-tie-metadata-and-docs.patch).

## Proposed PR title

```text
fix(strategy): expose voting tie metadata and document distinct ties
```

## Proposed PR description

```markdown
Fixes #247

As discussed in #247, this PR keeps exact-score voting and the default `tie_breaker="min"` behavior intact for backward compatibility while making tie resolution observable and documented:

1. **Documentation (`VotingEvaluationStrategy` docstrings & `docs/get_started/core_concepts.md`)**:
   - Clarify that voting aggregates by exact float equality: when all sampled scores are distinct, every score ties for first place and the default `tie_breaker="min"` selects the lowest score.
   - Recommend `AverageEvaluationStrategy` when averaging repeated continuous scores.
2. **Tie metadata (`VotingEvaluationStrategy.execute`)**:
   - Expose `max_frequency` (highest vote count observed) and `tie_resolved` (`len(highest_freq_values) > 1`) in `GraderScore.metadata` alongside `original_results`, so callers can tell whether a tie-breaker was used.
3. **Regression tests (`tests/evaluation_strategy/test_voting_evaluation_strategy.py`)**:
   - Add `test_execute_all_distinct_scores_reports_tie_and_selects_min` verifying `[0.85, 0.80, 0.72]` still returns `0.72` with `max_frequency == 1` and `tie_resolved is True`.
   - Add `test_execute_clear_winner_needs_no_tie_breaker` verifying a clear mode winner (`[0.85, 0.80, 0.85]`) skips tie resolution (`tie_resolved is False`, `max_frequency == 2`).
   - Verify `max_frequency == 2` and `tie_resolved is True` on existing multi-way tie cases.
```

## Local validation

- Offline unit tests (network sockets blocked, zero API calls):
  - `tests/evaluation_strategy`: **50 passed** (including all 15 tests in `test_voting_evaluation_strategy.py`)
  - `tests/runner/test_grading_runner_cancellation.py`: **24 passed**
- Code quality & formatting (`.pre-commit-config.yaml` rules):
  - `black --check --line-length=120`: passed (`2 files would be left unchanged`)
  - `isort --check --profile black`: passed
  - `flake8 --extend-ignore=E203,E704 --max-line-length=120`: passed
  - `pylint --max-line-length=120` (repo disables): **10.00/10**
  - Trailing whitespace check across all 3 modified files: passed
- Original pinned checkout `/Users/x/agent-eval/OpenJudge` remains untouched (`git status` clean).

## Commands to push and open PR (after owner approval)

```sh
git -C .cache/openjudge-contribution push -u fork fix/voting-tie-metadata
gh pr create --repo agentscope-ai/OpenJudge \
  --head Xxly959:fix/voting-tie-metadata \
  --base main \
  --title "fix(strategy): expose voting tie metadata and document distinct ties" \
  --body-file /tmp/pr_247_body.md
```
