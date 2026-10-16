# Sequence 270 — Privileged hosted audit path and planning safety

Canonical goal planning is now separated from execution, with prior verified projection wired into planning. Planning remains observational: it does not invoke executors or model inference. The execution CLI now recomputes current integrity pressure, throughput posture, risk budget, policy fingerprint, and integrity evaluation before allowing a mutation; stale plans cannot bypass current recovery or lockdown constraints.

The required quality gate now invokes both existing strict audit entrypoints through an explicit sudo root step on the GitHub-hosted runner. A new verifier refuses non-root execution and binds the audit result to the expected commit, tree, source digests, and unchanged source identity. Its report includes the actual effective UID and both command outcomes. The required gate uploads that report and the original audit artifacts. No privilege is simulated, and audit, immutability, or finalizer requirements are unchanged.

Validation: the focused planning, execution, runtime, hosted-workflow, privileged-wrapper, and mutation-custody regression selection passed (135 passed). The exact task acceptance nodes passed (17 passed), compileall passed, and targeted mypy passed for the changed CLI wrappers. Hosted root execution remains pending until this source is published and the required GitHub Actions check runs.

During custody preflight, the existing navigation index was found to contain a duplicate sequence row and stale derived byte-count, digest, and predecessor fields. The index now records the exact unchanged committed segment bytes in sequence order. No historical segment or evidence artifact was edited or removed. The strict continuation-custody verifier is still required to pass before publication.

