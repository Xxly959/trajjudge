# OpenJudge contribution survey (P5.0 draft)

Source: read-only checkout at `7d27246484e91c6ed4a349b6ebe7bd4629d9378f`; guide at `docs/community/contributing.md`.
Nothing here has been sent upstream. Opening an issue or PR needs the owner's explicit confirmation.

## Guide requirements (summary)

Type hints, docstrings (Args/Returns/Example), early validation; unit tests with `@pytest.mark.unit` and all LLMs mocked;
LLM graders also need `@pytest.mark.quality` tests against annotated data (skipped without API keys); docs under
`docs/built_in_graders/`; commit style `feat(grader): ...`; discuss bigger changes in an issue first.

## What already exists

- `TrajectoryAccuracyGrader` / `TrajectoryComprehensiveGrader` have unit tests and quality tests
  (`tests/graders/agent/trajectory/`), plus docs in `docs/built_in_graders/agent_graders.md`.
- `cookbooks/grader_validation` exists for validating graders against labeled data.
- Strategies (Direct / Average / Voting) exist in `openjudge/evaluation_strategy/`.

## Observations from our own use (verified in code or by a test of ours)

1. `TrajectoryAccuracyGrader._aevaluate` clamps the model's score to [1, 3] and stores the *clamped* value
   in `metadata["raw_score"]`; a model output such as 99 becomes 3 with no signal. Our wrapper has to re-parse the
   raw completion to detect it (`judging.check_raw`). (Source: `trajectory_accuracy.py`, `score = max(1.0, min(3.0, result.score))`.)
2. On empty messages the accuracy grader returns `score=0.0`, which is outside its documented 1-3 scale.
3. Voting/Average strategies repeat identical requests; with any response cache keyed on the request they collapse to one sample.
   This is a caller-side caveat (ours was fixed with a per-call repeat id), possibly worth a docs note.

## Candidate contributions (ranked by safety, decision after P2-P4 results)

- **A. Cookbook: robustness audit of an agent-trajectory grader** (labeled set + benign perturbation harness + metrics).
  Fits the repo's `cookbooks/` layout; depends on our RQ3 results and needing a license-checked, redacted fixture set.
- **B. Small fix + tests for observations 1 and 2** (raw score preserved in metadata, empty-input handling) after an issue
  discussion confirms the intended behaviour. Smallest, most reviewable.
- **C. New grader** only if experiments reveal a concrete gap; requires an issue first.

Pre-PR checklist (to run later, not yet done): fork is up to date with `agentscope-ai/OpenJudge` main; `pytest -m unit` passes;
no keys/trajectories with private data; license of any fixture checked (Claw-Eval MIT, OpenJudge Apache-2.0);
commit message `feat(grader): ...` / `fix(grader): ...`.
