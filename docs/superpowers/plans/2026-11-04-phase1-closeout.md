# Phase 1 Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Generate an evidence-based v0 report and prove offline cache replay and clean-clone tests.

**Architecture:** Reuse the completed S5 manifest and S6 cache keys. The phase1 entry point forces offline scoring and then calls a standard-library report generator. The report joins by real trace identity, retains missing/error outcomes, and recomputes costs from the shared usage ledger.

**Tech Stack:** Python 3.11–3.12, existing pytest/OpenJudge environments, standard library, existing YAML pricing reader; no new dependencies.

**Spec:** User-approved S7 requirements and `docs/DECISIONS.md` (D19–D22).

## Global Constraints

- Only phase 1; no human labels, stability experiments or injection experiments.
- DeepSeek only; total budget USD 3; this gate makes zero paid requests.
- Upstream OpenJudge and Claw-Eval are read-only, at the recorded commits.
- Separate uv environments; do not install Claw-Eval into the judge environment.
- Never print or commit credentials; `.env`, raw traces, usage and response caches stay ignored.
- English code/docstrings/README/report; Chinese execution notes.
- One commit for the entire S7 gate, as explicitly requested by the user.
- Continue in the existing approved checkout so sibling upstream paths and evidence remain valid.

## Review Focus

- Missing/error verdicts must remain visible in the two-trace denominator.
- Foreign or duplicate rows must never silently overwrite a result.
- Cached logical tokens must not count as paid tokens, even after repeated report regeneration.
- Missing/corrupt ledgers and unknown prices must not produce a misleading zero-cost success.
- Fresh paths, absent credentials and blocked sockets must not make offline replay contact an endpoint.

### Task 1: Validated deterministic report

**Files:** Create `src/trajjudge/reporting.py`, `scripts/report.py`, `tests/test_reporting.py`.

**Interfaces:** `generate_report(pilot_path, scores_path, usage_path, pricing_path, output_path) -> ReportResult`; result carries markdown and completion status. Reads S5 JSON, native JSONL identity/grading events, S6 JSONL and UsageLog; writes Markdown atomically.

- [x] Write failing tests for joined score rows, independent scales, paid/cache cost accounting, deterministic output, missing/error verdict visibility, duplicates/foreign traces, unknown cost and absent ledger.
- [x] Run the focused tests and observe failure before adding implementation.
- [x] Implement validation, one row per pilot trace, stage/per-role cost summaries and known limitations. No quality correlation or reliability claims.
- [x] Run focused tests; inspect report output and reconcile actual ledger totals.

### Task 2: Offline entry point and reproducibility

**Files:** Modify `scripts/run_phase1.py`, `README.md`, `Makefile`; create `tests/test_phase1.py`; update `notes/log.md`, `docs/DECISIONS.md`, `reports/phase1.md`.

**Interfaces:** `make phase1` invokes the existing `score_trajectories.main(['--offline'])` and Task 1 report generation. A cache miss, invalid result or unknown accounting returns nonzero while retaining error evidence.

- [x] Add and run failing offline entry tests with two mocked native model completions, replay-only cache, forbidden network and no credentials.
- [x] Implement offline orchestration, report CLI and clear failure diagnostics.
- [x] Rewrite README around project goal, three research questions, Mermaid pipeline, pinned upstream commits, separate environment setup, original pilot vs cached replay, and limitations.
- [x] Run `make phase1` with socket access blocked and credentials absent; delete only disposable derived output copies and prove reconstruction from actual caches.
- [x] Test a disposable clean clone with a new judge venv and read-only sibling sources, without secrets or prior outputs. Record exact scope of setup/network and offline test results.
- [x] Request one independent read-only S7 review; fix important findings with failing regression tests.
- [x] Run complete tests, staged secret checks, upstream clean checks and `git diff --check`; commit once using `feat(s7): ...` and stop.

## Progress

- Initial read: S6 commit `9800ce5` is clean. `run_phase1.py` is a placeholder, and README status still says S1–S5; both are in scope.
- Design choice: replay native graders from cache before reporting, rather than trust a stale score file. Direct `scripts/report.py` remains available for existing evidence.
- Design choice: report timestamps and totals describe original paid evidence; replay cache counts are reported separately so repeated runs remain byte-identical.

- Task 1: complete. Initial 14 RED cases became GREEN; pending-accounting and review regressions also verified RED then GREEN.
- Task 2: complete. Full current and clean-clone suites: 104 passed. No-key socket-blocked cache reconstruction, repeated/cross-checkout byte identity and fatal cache-miss behavior verified.
- Final review: two important findings (mixed modes and nonfinite digest failure) fixed, with seven regression cases; no unresolved review findings. Original mode/token usage is joined to paid evidence.
- No new paid calls, dependencies or phase-2 functionality. Validation details are in notes/log.md; machine-readable local evidence is outputs/verification/s7.json.
