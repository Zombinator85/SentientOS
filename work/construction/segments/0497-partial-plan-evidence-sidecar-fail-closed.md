# Sequence 497 — fail closed on a partial plan evidence sidecar

PR #2494 adds a regression for a crash between writing the external evidence-binding sidecar and its envelope. A sidecar alone marks the persisted plan as evidence-bound: direct execution without the expected digest raises `work_plan_evidence_digest_required` before task invocation, journal creation, or run artifact creation. The test also confirms the partial sidecar bytes remain unchanged.

The affected executor, CLI, evidence bounds, journal, plan loading, and orchestration tests passed locally (85 tests), and `git diff --check` passed. On exact candidate `822432e2d35c4be140db6727265c105588409981` (tree `03da01b4f4d39d592c32d210f3bed990a609dd4a`, based on main `c43cd5db8ab7871623f12f9c7c934ca96fe22d6e`), Required Quality Gate run `39409641654`, CI `39409641671`, Invariant Tests `39409641721`, Gradient `39409641646`, Codex CI `39409641630`, Release `39409641632`, Docker `39409641665`, and Lint Benchmark `39409641675` all passed. The Quality Gate's hosted strict audit, acceptance, privileged finalizer, and separate pre-publication metadata guard passed for the exact candidate; its downloaded artifact digest was independently verified. The profile was solo; no exhaustive matrix was requested.

PR #2494 merged with commit history preserved as `50c1d9ab99d8d81b0a28ba58185c8a99349b17ca`. Main readback returned the exact test source, blob `6624dfd70bdf40cc22a4810db3557f6003d0a3c7`. The merge retains the candidate tree `03da01b4f4d39d592c32d210f3bed990a609dd4a`.

No production task, inference, campaign, or transition was executed.
