# Free continuation plan

Spec: owner's recovery and P2–P5 handover; current evidence in STATE_RECOVERY.md.
Execution: inline in this checkout, preserving original data and labels. No paid
completion or external write. Existing independent upstream environments remain.

- [x] Annotation: regression tests for complete views, exclusive template
  creation, duplicate labels, interrupted saves; fix `annotation.py` and CLI.
  Freeze selected trace/source hashes and cap cohorts; build 50 blank items.
- [x] Judge reliability: regression tests for changed model/input/cap on resume,
  malformed comprehensive steps and interrupted checkpoints. Use atomic per-job
  files with run manifest under `runs/`; never silently reuse mismatched results.
- [x] Offline reporting: join real labels only, retain missing/error counts;
  paired stability/injection summaries with trace-level bootstrap intervals.
  Add safe default estimate/analysis commands; no auto-started paid run.
- [x] P4 free controls: run original plus benign variants through rule graders;
  report lexical changes honestly, without calling them LLM robustness results.
- [x] P5: isolated local OpenJudge contribution branch and reviewable draft;
  final-status report, resume draft and Chinese walkthrough with ten questions.
- [x] Verification: full offline suite, phase1 hash replay, secret/diff checks,
  upstream status and process check; update PROGRESS and commit each milestone.

Review focus: never overwrite owner labels; never hide truncated evidence;
input/model/cap changes must not be skipped on resume; missing repeats and failed
grades must remain visible; multiple variants/repeats of one trace are not
independent bootstrap samples. Paid execution, labels, final claim approval and
external submission remain owner gates.
