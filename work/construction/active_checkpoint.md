# Active construction checkpoint

## Current verified state — sequence 583

Sequences 582–583 replace tick-collision-prone epistemic scheduling with deterministic least-generation-first state service and reconcile its hosted evidence. The same-tick restart regression passed in source validation. PR #2622's strict privileged audits, finalizer, metadata guard, complete CI, and other candidate checks passed; PR #2623's evidence integration passed all checks and main matches its merge tree.

Latest verified main: `ace641fae2200401143d87e57b8eea38b50793b8`, tree `3633d3fb0e13946778255ef06622cae6ebc49ee1`
Latest construction segment: `work/construction/segments/0583-reconcile-sequence582-integration.md`
Latest segment SHA-256: `5265685e85fc1d0317dd414934da00294c93db7115f13e7e0cde2edb3ed02912`
Sequence: 583 (verified evidence integration)

Next: verify that service fairness depends on state-generation count rather than evidence volume. Exercise unequal active-binding sets, ensure candidates omitted from a tick do not advance, and ensure receipt recovery cannot make a pending or rejected update appear served. Keep the per-tick and per-proposition bounds and mutation authorization intact.
