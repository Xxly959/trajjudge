# Third-party provenance and artifact release boundary

| Dependency | Pinned commit | Local license inspected |
| --- | --- | --- |
| Claw-Eval | 5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7 | MIT, Copyright (c) 2026 claw-eval |
| OpenJudge | 7d27246484e91c6ed4a349b6ebe7bd4629d9378f | Apache License 2.0 |

Both original worktrees remain read-only and clean. The contribution patch is
prepared in a separate local clone. Nothing has been published externally.

Existing structural fixtures in `tests/fixtures/claw_s5` are redacted derivatives
of two generated task trajectories; `provenance.json` records task ids, source
hashes, upstream revision, sidecar selection and redactions. They are not human
labels or a grader quality dataset. A copy of the benchmark's MIT notice is
retained alongside them for benchmark-derived portions. This does not assign
that license to every generated/model-authored passage or establish release
rights to all possible external content.

No new raw traces, labels, API responses, sidecars or private texts were added to
Git in this continuation. Before any public dataset release, review every file
for personal data, credentials, external-content and generated-output rights,
retain applicable notices, and obtain the owner's release approval. Do not
assume that a framework's software license licenses all inputs or outputs.
