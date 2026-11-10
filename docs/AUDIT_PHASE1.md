# Phase 1 audit

Audit date: 2026-11-04. Auditor: handover assistant. Everything below was run or
read by me, not copied from `notes/log.md`. Verdicts: PASS / PARTIAL / FAIL.

Summary: 6 PASS, 5 PARTIAL, 2 FAIL counting item 6 (fixed here) and item 8 (open).
Nothing blocks Phase 2 planning. Items marked **ASK** need your decision.

## 1. Git status and history: PASS (minor notes)

- `git status`: clean on `main` before the audit.
- 8 commits, roughly one per gate (skeleton, fix(s1), s2, s3, S4 docs, s5, s6, s7). Messages follow `type(scope): ...`.
- Each commit mixes code, tests, README, log and DECISIONS. Acceptable for a gate history; later phases should use smaller commits.
- `docs/superpowers/plans/2026-11-04-phase1-closeout.md` is tracked. It is a tool-generated plan, not project documentation. **ASK**: delete or keep?

## 2. Upstreams untouched: PASS

| Repo | HEAD | Remote | `git status --short` |
| --- | --- | --- | --- |
| `../claw-eval` | `5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7` | `claw-eval/claw-eval` | empty |
| `../OpenJudge` | `7d27246484e91c6ed4a349b6ebe7bd4629d9378f` | `Xxly959/OpenJudge` (your fork) | empty |

Both match the README. The OpenJudge remote is your fork, not `agentscope-ai/OpenJudge`.
Before any PR, check how far the fork is behind upstream.

## 3. Offline tests: PASS (with an environment caveat)

- `env -u DEEPSEEK_API_KEY make test` inside the tool sandbox: 102 passed, **2 failed**
  (`test_claw_bridge.py::test_provider_binding_works_after_spawn` and `::test_actual_bounded_worker_bootstrap_in_spawn`).
  Cause: `PermissionError` creating a POSIX semaphore for `multiprocessing` spawn. This is a sandbox restriction, not a code defect.
- The same file run outside that sandbox: 7 passed. Full suite is 104 tests; none skipped or xfailed (grep of `tests/` finds only function names containing "skips").
- Mocking is real: tests inject a `transport` double (`Recorder`) into `LLMClient`; the autouse fixture `block_network` in `tests/conftest.py` makes `socket.connect/getaddrinfo` raise; settings use `api_key="unit-test-key"` and `https://example.invalid`.
- Limit: I did not run on a physically offline machine; the socket block is the evidence.
- Gap: the two multiprocessing tests fail in sandboxes that deny semaphores (some CI containers). Documented, not changed.

## 4. Reproducibility of `make phase1`: PASS

Procedure: copied `outputs/` to `/tmp`, deleted `outputs/grades/s6-offline*`, `outputs/grades/adapted` and `reports/phase1.md`, kept `.cache/llm` (20 entries), ran `env -u DEEPSEEK_API_KEY make phase1`.

- Exit 0. `reports/phase1.md` SHA-256 `1eb5ca65...` is **identical** before and after.
- `outputs/usage/usage.jsonl`: 50 -> 54 rows. All 4 new rows are `cached: true` (the OpenJudge replays). Rows with `cached: false` stay at 20, all `status: success`. So no paid request was made.
- Evidence strength: ledger plus the client's offline mode (a cache miss raises). My socket-deny wrapper did not propagate because `run_phase1.py` spawns subprocesses, so I do not count it.
- `s6-offline.jsonl` is not byte-identical to the original (timestamps and cached flags differ); the report is.
- Re-ran after my `llm.py` change (item 6): report still identical, so legacy cache keys remain valid.

## 5. Secrets: PASS

- `git grep -n "sk-"`: only prose in docs/log/report and the regex in `src/trajjudge/secrets.py`. No key-like strings.
- History: `git log -p --all | grep -E "sk-[A-Za-z0-9]{10,}"` returned nothing.
- `git ls-files | grep '^\.env'`: only `.env.example` (placeholder `<your-deepseek-api-key>`).
- `git check-ignore -v .env`: ignored by `.gitignore:2`. I looked at `.env` only in redacted form.
- Not checked: ignored local files (`outputs/`, `.cache/`) were not grepped for the key.

## 6. Cache key: FAIL, fixed

Before: key = SHA-256 of {version, base_url, model, thinking, messages, full request (temperature, max_tokens, reasoning_effort, response_format, extra_body), tools}. Model, thinking, parameters and input were covered. There was **no `repeat_id`**, so repeated identical calls would always hit the cache and silently invalidate RQ2.

Fix (uncommitted in working tree):
- `LLMClient.complete(..., repeat_id: int | None = None)`; when not `None` it enters the key payload. `None` leaves the key unchanged, so the Phase 1 cache and report stay valid (verified in item 4).
- Tests added in `tests/test_llm.py`: `test_repeat_id_gives_independent_cache_entries`, `test_no_repeat_id_keeps_legacy_cache_key`. All 27 tests in that file pass.
- Still open: `repeat_id` is not yet passed through `openjudge_bridge`/`runner` or stored in usage rows. That is P3 infrastructure.
- To verify in P3, not assume: whether `temperature` is honoured in thinking mode. Sampling parameters in the key matter only if they take effect.

## 7. Adapter: PARTIAL

Good:
- Golden tests on two redacted real traces (`tests/fixtures/claw_s5/`, `provenance.json` lists redactions): a 2-call and an 8-call trace.
- Raw events, unmapped blocks and unknown events are kept in `metadata` (`events`, `unmapped_content`, `unmapped_event_indices`); tested.
- `tool_call_id` pairing validated by `validate_tool_links`; a mismatch test exists.

Gaps:
- `tool_result.is_error` is kept in metadata only and is **not visible to the judge**. The test asserts the metadata flag, not a mapped error. Whether this matters depends on how Claw-Eval marks failures; unverified.
- No dedicated tests for: no tool calls, empty assistant content, or parallel tool calls in one turn built from scratch (only incidentally covered by the real email fixture).
- Any unmapped block makes `runner` refuse to score. Safe, but may reject traces at P2 scale.
- Proposal: add the three edge-case tests (small). Mapping `is_error` is a design choice. **ASK**.

## 8. Runner output: FAIL (partial)

Fields in `outputs/grades/s6.jsonl`: `trace_id, grader, score, reason, judge_model, thinking, openjudge_commit, timestamp, usage, metadata, status`.

- Missing: `repeat_id`; a separate grader version (name plus OpenJudge commit pins the code, which is arguably enough).
- Rule graders correctly have `judge_model=None`, `thinking=None`.
- Not changed now: new `GradeRecord` fields touch the report's evidence hash and need plumbing. Planned for P3. **ASK** if you want it before the ROADMAP.

## 9. Report honesty: PARTIAL

Re-computed from raw artifacts:
- Totals from `outputs/usage/usage.jsonl` uncached rows: 20 calls (19 completions + 1 model discovery), 54,064 input / 2,874 output tokens, peak-price cost $0.019668. The report states the same.
- Stage splits (S2 5/493/69; S3 1/504/38; S5 9 calls; S6 4/14,339/606) match.
- All 8 rows of `s6.jsonl` match the report table (e.g. T010 comprehensive 0.71875; T002 observation gain 0.847253; accuracy 3.0 on both). Official task_score 0.804 / 0.85 match the trace `grading_result`.
- Deviations are stated: DeepSeek replaces Gemini/Claude, not leaderboard-comparable, one trial.
- No placeholders or invented numbers found.

Problems:
- "Runtime differences" says "judge thinking enabled with default effort" (Claw framework judge) while the table says OpenJudge ran with thinking disabled. Both are true for different judges but confusing; reword.
- n=2, both pass officially and both get accuracy 3.0: the report correctly claims nothing about reliability.
- I could not re-derive LLM scores (they come from cached model replies); I confirmed only that stored scores equal reported scores.

## 10. Documentation: PARTIAL

- README has goals, RQs, pipeline diagram, reproduction steps and limits and matches the code. `DECISIONS.md` has D1-D22; the historical local log was 1,120 lines at audit time.
- Missing: single provider and self-preference are not listed as limitations (constraint 7). To add.
- Missing: a decision entry for `repeat_id`.
- `configs/pricing.yaml` has no `deepseek-v4-pro` price, so pro calls would be refused as unpriced. I need the official figure; I won't guess. Needed before P3.

## 11. Cost: PASS

- Every completion has a usage row (`cached`, tokens, `raw_usage`, `status`, `tag`, `thinking`, `model`, `timestamp`); cached replays are logged too.
- Cumulative Phase 1 spend at peak cache-miss prices: **$0.019668** (budget USD 3). An estimate, not the invoice; the DeepSeek console is authoritative.
- Rows store no per-row USD; cost is derived from `pricing.yaml` at report time.

## 12. Code quality: PARTIAL

- Light dependencies (`openai`, `PyYAML`, pytest). Type hints used widely.
- Dense style in `adapter.py`/`runner.py`; some public methods (`AdaptedTrace.to_dict`, `GradeRecord.to_dict`) lack docstrings.
- No ruff/pyflakes installed, so no mechanical lint or dead-code check. `use_cache` in `complete()` is a documented no-op, i.e. dead surface.
- No refactor proposed now.

## Changes made

Uncommitted, awaiting your go-ahead to commit as `fix(llm): add repeat_id to cache identity`: `src/trajjudge/llm.py`, `tests/test_llm.py`, and this file. Nothing else changed; nothing pushed.

## Open decisions (ASK)

1. Delete `docs/superpowers/` (tool-generated)?
2. Map `is_error` into the judge-visible tool message, or keep it metadata-only?
3. Add `repeat_id` and grader version to runner output now, or in P3?
4. Provide the official `deepseek-v4-pro` price for `configs/pricing.yaml`.
5. Remove the no-op `use_cache` parameter?
