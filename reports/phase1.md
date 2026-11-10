# Phase 1 report v0

Integration evidence from 2 small benchmark runs; no human labels, stability or injection experiments.

Paid evidence through: 2026-11-04T12:05:02+00:00.

## Per-trace results

Claw framework scores below were re-evaluated with DeepSeek and are **not leaderboard-comparable official Gemini/Claude labels**. Different scales/rubrics are shown without rescaling or calculating agreement.

| Task | Trace ID | Claw framework (0–1) | Accuracy (1–3) | Comprehensive (0–1) | Action loop (0–1) | Observation gain (0–1) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| T010_contact_lookup | 371e8b9e-5e14-4e6a-ac77-1e0af4d19d83 | 0.804000 | 3.000000 | 0.718750 | 1.000000 | 0.979167 |
| T002_email_triage | 5a4c129f-bc96-45cc-a1c4-b485336b60d1 | 0.850000 | 3.000000 | 0.875000 | 1.000000 | 0.847253 |

Status: complete. Valid verdicts: 8/8; retained traces: 2.

## Tokens and conservative cost

| Stage / role | Actual completion attempts | Input tokens | Output tokens | Estimated USD |
| --- | ---: | ---: | ---: | ---: |
| S2 probe | 5 | 493 | 69 | $0.000231 |
| S3 weather | 1 | 504 | 38 | $0.000197 |
| S5 agent | 7 | 37346 | 1013 | $0.012420 |
| S5 framework judge | 2 | 1382 | 1148 | $0.001793 |
| S6 OpenJudge | 4 | 14339 | 606 | $0.005029 |
| **Phase 1 total** | **19** | **54064** | **2874** | **$0.019668** |

Prices use peak input cache-miss and output rates. Provider prompt-cache/off-peak discounts may reduce the invoice. Stage rows round upward to six decimals; the total is independently calculated from unrounded ledger amounts.

Scoring artifact: 4 disk-cache hits, 0 actual API attempts. Cached logical tokens and zero-token model discovery are excluded from paid totals. Regenerating this report makes no paid requests.

## Provenance and reproduction

- Claw-Eval commit: `5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7`.
- OpenJudge commit: `7d27246484e91c6ed4a349b6ebe7bd4629d9378f`.
- OpenJudge model modes: deepseek-flash / thinking=false.
- Pricing SHA-256: `b519d1a247690362c65e2188b01f9e2f0db7e67da13895f273d8ecec1acf153d`.
- Stable evidence SHA-256 (native source hashes, verdicts, actual ledger rows): `a44b561901d3e8d284436a2b4f82a725190ff374548cf5530ee6b4bc54e40766`.

With the ignored S5 artifacts, full response cache and usage ledger restored under the current project, run `make phase1`. It replays native OpenJudge scoring offline before reporting. Missing cache entries stop execution; no endpoint fallback is allowed. Use `python scripts/report.py` to render existing score artifacts only. See [README](../README.md) for pinned source checkout and separate environment setup.

## Runtime differences from the benchmark

- DeepSeek agent and grader replace upstream model choices; not leaderboard-comparable
- one trial; no Pass^3 estimate
- agent thinking disabled; judge thinking enabled with default effort
- shared non-streaming transport replaces native streaming and layered retries
- network timeout is 60 seconds instead of native provider 300 seconds
- agent max_tokens=1024; judge max_tokens=8192; serial quotas and USD 0.75 reservation
- input estimate cap raised from the provisional 16k to 48k after measuring native schema size
- mock ERROR_RATE explicitly zero; implementation default preserved
- OpenJudge uses JSON-object output with original-schema local validation before callbacks; full step coverage and raw score checks reject malformed verdicts.
- OpenJudge thinking is disabled; the native Claw framework judge retains thinking enabled. No upstream files or original scoring formula were changed.

## Known issues and limits

- One provider and 2 general text tasks, one trial per task; no statistical agreement, cross-provider generalization or reliability conclusion is supported.
- Framework scores use the original task rubric with a different judge model; they are not human labels. The benchmark safety fixtures were preserved, with no new injection experiment.
- Mismatched rubrics and a tiny sample prevent a meaningful correlation claim, even when some scores coincide.
- Native Comprehensive excludes original system text from its prompt. It measures assistant tool-call batches (2, 3 here), not individual tool invocations (2, 8). Its four raw dimensions use 1–5 and the overall score uses 0–1.
- Action-loop and observation-gain rules use word-set/Jaccard overlap (thresholds 1.0 and 0.5); they do not establish semantic correctness, information utility or task success.
- Native trace JSONL lacks initial system text; matching request sidecars supply it. Raw events and unmapped fields remain in adapter metadata. Partial semantic mappings are not scored.
- T002 native judge_calls is empty despite a paid direct judge-client request; the shared ledger includes it. TraceEnd default scores and grading_result efficiency zeros are not used as task outcome/turn-count labels.
- Local non-streaming IO, output caps, timeouts, bounded retries and native mock environments differ from leaderboard execution. The upstream weather example is a smoke fixture, excluded from the per-trace comparison.
- Raw trajectories, request sidecars, response caches and usage are ignored local evidence; a source-only clone can run mocked tests, but offline report regeneration also requires those artifacts.
- Human annotation, repeated-run stability and prompt-injection audits remain future work; none was implemented in phase 1.
