# 0098 — Recover fully scored interrupted developmental trials without replay

Source baseline: `cce384313f81b0745bdfd47c8c9d948dfdd90ebf`, tree `fce3a67ff4f39ad31594f8b44e1583e4d6ab075a`. Per-condition outputs, cognition observations, and score checkpoints were durable, but a crash after the final score and before aggregate run publication stranded a fully measured trial as an incomplete tick with no source-selectable run.

The resident cognition owner now binds the preregistered objective protocol and task-plan digest to the tick intent before inference. On restart, it reconstructs an aggregate run only when all three condition observations and score checkpoints independently validate against that protocol, source receipt, invocation digest, and original snapshot intent. The reconstructed run uses immutable `persist_run` custody and is reloaded through the normal verifier. A bounded accessor returns only verified `(run_id, run_digest)` pairs for existing explicit World-State selection.

The original tick remains marked interrupted and cannot be replayed. If the final score checkpoint is missing, recovery leaves the trial incomplete and exposes no run. No inference or effect is replayed.

The three affected hermetic modules passed **101 tests, 0 failed, 0 skipped**. Changed Python files compiled and `git diff --check` passed. Targeted mypy was attempted; repository import/config diagnostics prevented a clean result (1,092 diagnostics across 144 files), with none reported in the newly added recovery helper. Evidence: `work/construction/evidence/0098-interrupted-objective-run-recovery-junit.xml` and `work/construction/evidence/0098-interrupted-objective-run-recovery-results.json`.

This verifies owner-produced fixture receipts and immutable recovery semantics, not actual local-model performance or production behavior. Production remains unverified.

Next: inspect the runtime-generation observation boundary against its exact launcher and installation owners; retain `not_independently_attested` if loaded-code identity has no independent issuer, then continue with any concrete downstream source gap.
