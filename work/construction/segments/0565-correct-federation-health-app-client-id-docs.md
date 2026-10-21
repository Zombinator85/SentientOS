# Sequence 565 — correct Federation Health App setup guidance

PR #2590 corrected the GitHub App setup guide to name the configured `SENTIENTOS_FEDERATION_HEALTH_APP_CLIENT_ID` secret that the workflow actually passes as the action's `client-id`. A hosted workflow contract assertion now keeps the guide aligned with the Client ID secret, private-key secret, and opt-in repository variable. Publisher authority and workflow behavior did not change.

The candidate `277a87bdeea216d1543e5554117bd76a75862af3` was based on verified main `1de9d1280180342b2b5abeb986523e249e3dc81c`, with tree `5fc1d8879f5d8f42dcdc2c2267bc26ad5e377fba`. All 20 reported candidate check runs completed: 18 succeeded and the two publisher-only steps were conditionally skipped. The 47-node Required Quality Gate passed with actual Administrator authority, strict hosted finalization, and its separate pre-publication metadata guard. The exact-candidate acceptance and finalizer artifacts were retained by GitHub.

PR #2590 merged normally as `597af64de9c6382639b0b97e97d8718864538a6f`, preserving the candidate as second parent and verified main as first parent. The merge tree `5fc1d8879f5d8f42dcdc2c2267bc26ad5e377fba` equals the candidate tree.

Post-merge CI, Required Quality Gate, Invariants, Docker, Docs Deploy, Codex CI, and Nightly Self Check all passed on the resulting main SHA. Forge Smoke was conditionally skipped.

This increment only aligns operational documentation and its contract test. The configured credential value was not accessed or recorded. Federation Health publication works, while its current report still reflects a stale configured local snapshot rather than live federation telemetry.

Verified main: `597af64de9c6382639b0b97e97d8718864538a6f`, tree `5fc1d8879f5d8f42dcdc2c2267bc26ad5e377fba`
Latest construction segment: `work/construction/segments/0565-correct-federation-health-app-client-id-docs.md`
Sequence: 565 (verified documentation integration)

Next: reassess the developmental outcome-to-planning dependency against the current runtime and acceptance suite, identifying a still-missing canonical connection before implementing further changes.
