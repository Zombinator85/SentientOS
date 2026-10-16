# 0104 — Reconcile published scorer, cold restart, and terminal checks

Source baseline: `b9ce905af905920d0c21e260eef73de6a9708ac5`, tree `deb351e76e9cf50b4720c66bbbd25bd6a521914b`.

Fresh GitHub branch read confirmed this exact head and tree before review. The scorer and targeted typing work from sequences 102–103 are already published; this isolated workspace contained no later unpublished source changes. No scorer work was reconstructed or discarded.

The sequence-103 hosted checks are terminal: Source Validation (unprivileged) succeeded, Helm Kubernetes smoke succeeded, and docs, self-check, and invariants failed. This records hosted status only; those protected jobs were not rerun. Prior check logs attribute failures to protected administrator-only state and `/glow` access restrictions, not to the focused scorer path.

A fresh focused run over the scorer, history-intervention, model-replacement, resource-lineage, and resident-cognition suites passed **124/124**, with no skips. The cross-process test reconstructs installation-scoped resource evidence, the daemon World-State board, persistent epistemic state, developmental history, and self-model in a child interpreter; later cognition consumes the reconstructed evidence. It passes without a serialized predecessor World-State snapshot or replaying inference. The exact command is in evidence JSON. Changed integration owners compile, and targeted mypy reports no issues in the two experiment modules. Ordinary repository-wide import-following mypy remains non-clean at the previously observed 507 diagnostics across 87 files.

The persisted raw cognition answer is retained only in the bounded, receipt-bound developmental candidate so recovery can parse it again and verify the exact authenticated output digest before candidate admission. The objective scorer itself does not retain raw prompts or outputs. Removing the candidate's exact source bytes without an equivalent authenticated receipt-byte custody path would weaken restart verification, so no speculative privacy rewrite was made.

Fixture experiments establish scorer correctness and treatment-associated fixture outcomes, not real-model learning. No local model, provider, or production serving path was invoked. Genuine local-model transfer remains blocked on an operator-commissioned model artifact with authenticated development provenance, an explicitly admitted local serving/inference route, and real invocation receipts. Loaded Python module identity likewise remains `not_independently_attested`; executable-image observation is not loaded-code attestation.

No production verification occurred and no runtime code changed in this checkpoint. Next dependency: use the existing commissioning and serving owners to prepare/execute the preregistered objective protocol only after those external artifact and admission prerequisites are supplied; otherwise continue with source-backed experiment readiness that does not claim a model effect.
