# Upstream Issue Proposal: `VotingEvaluationStrategy` degenerates to `min-of-N` on continuous-valued graders

Status: **CLOSED (resolved via merged PR [agentscope-ai/OpenJudge#248](https://github.com/agentscope-ai/OpenJudge/pull/248), merge commit `15d22f2ca4e20413bc91f6f52ee65d5bee12b3cd` at `2026-11-18T06:54:47Z`; originally submitted as [agentscope-ai/OpenJudge#247](https://github.com/agentscope-ai/OpenJudge/issues/247)).**
Audited upstream commit: `7d27246484e91c6ed4a349b6ebe7bd4629d9378f` (`openjudge/evaluation_strategy/voting_evaluation_strategy.py`), confirmed unchanged on `main` (`a850e78`).

## Problem Summary

`VotingEvaluationStrategy` aggregates `num_votes` evaluations by counting exact floating-point matches via ` collections.Counter(values).most_common()` and breaking ties with `tie_breaker` (which defaults to `MIN`).

While exact mode counting is well-behaved on discrete integer scales (e.g., `TrajectoryAccuracyGrader` returning `{1, 2, 3}`), **continuous or step-averaged graders** such as `TrajectoryComprehensiveGrader` (returning normalized step-mean floats in `[0, 1]`, e.g., `0.7833`, `0.8167`, `0.8500`) almost never produce bitwise-identical floats across independent LLM samples when step scores vary.

Whenever all `N` sampled scores are distinct:
1. Every candidate score has frequency `1` in `Counter(values)`.
2. All `N` scores enter the tie-breaking branch.
3. With default `tie_breaker="min"`, `VotingEvaluationStrategy` deterministically selects **`min(values)`** — turning "majority voting" silently into a **worst-of-N minimum filter**.

## Empirical Observation in TrajJudge Audit

In our paired aggregation audit (`reports/robustness_v2.json` and `reports/v1_vs_v2_stats.md` §5):
- Across 22 recovered `TrajectoryComprehensiveGrader` 3-vote panels, all 3 draws were distinct in **9/22** panels, and `voting == min(3 draws)` occurred in **15/22 (68.2%)** panels (`voting < average` in **12/22** panels).
- Callers selecting `VotingEvaluationStrategy` expecting variance reduction around the central tendency instead induce a systematic downward bias relative to `Direct` and `AverageEvaluationStrategy`.

## Minimal Offline Reproduction (Zero API Calls)

```python
import asyncio
from openjudge.evaluation_strategy import VotingEvaluationStrategy
from openjudge.graders.schema import GraderScore

async def demo():
    draws = iter([0.85, 0.80, 0.72])
    async def fake_eval(**_):
        return GraderScore(name="comprehensive", score=next(draws), reason="step mean")

    strategy = VotingEvaluationStrategy(num_votes=3)
    out = await strategy.aevaluate(fake_eval)
    # Expected central-tendency behavior: ~0.80 (median) or warning on continuous tie
    # Actual behavior: 0.72 (minimum of all 3 draws)
    assert out.score == 0.72

asyncio.run(demo())
```

## Proposed Upstream Options

1. **Option A (Non-breaking warning + `MEDIAN` tie-breaker)**: Add `"median"` to `TieBreaker`, document in `VotingEvaluationStrategy` that continuous graders without exact modes trigger `tie_breaker` on nearly every panel, and emit a `UserWarning` (or metadata flag `metadata["all_votes_distinct"] = True`) when `max_count == 1`.
2. **Option B (Optional tolerance binning)**: Add an optional `bin_width: float | None = None` parameter (default `None` to preserve exact backward compatibility) so continuous graders in `[0, 1]` can vote over quantized buckets (e.g., `bin_width=0.05`) before breaking ties.
