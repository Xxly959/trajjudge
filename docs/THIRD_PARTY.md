# Third-party provenance and artifact release boundary

| Dependency | Pinned commit | License |
| --- | --- | --- |
| Claw-Eval | 5680b8b11ff2ee5dd2b07b89086a29a5c5c984d7 | MIT, Copyright (c) 2026 claw-eval |
| OpenJudge | 7d27246484e91c6ed4a349b6ebe7bd4629d9378f | Apache License 2.0 |

The dependencies are installed from their respective source checkouts. The
OpenJudge contribution is included as a patch and an unsubmitted draft.

The two fixtures in `tests/fixtures/claw_s5` preserve event and message structure
with synthetic prompts, requests, observations and final answers. They contain
no human annotations. The Claw-Eval MIT notice is included for portions derived
from the benchmark. `provenance.json` describes the fixture scope.

Raw trajectories, original sidecars, API responses, cache, credentials, private
run logs and labels remain local. The committed experiment reports contain
aggregate results. A future dataset release requires a separate review of
personal data, credentials, and rights to all inputs and generated outputs.
