# Sequence 574 — clarify embodiment observation test contracts

Three adjacent failures in `tests/test_embodiment_self_observation.py` reproduced unchanged on the verified pre-change tree `bb0a4401e9648c8523bdd319befe97ddfae8104e`. The tests had stale expectations: an inert board must still preserve its built-in non-authorizing quarantine-custody observation; restored synthetic caller sensor evidence remains historical with unknown freshness and cannot claim current truth; and descriptor-relative publication failures are wrapped as `PrivateFileCustodyError(publication_unavailable)`.

PR #2611 updates those test contracts without changing runtime source. The focused file passed all 14 tests in an isolated environment; the canonical epistemic-planning module passed both tests. Compilation and whitespace checks passed. The changed test blob was read back byte-for-byte from GitHub, and the complete non-truncated candidate tree contained 8,180 entries.

The exact candidate `15819c0a53b749b55b5773c827373ac90cdc92c0`, based on verified main `bd8ffa6a5fab52e677fa32d58fa902e0e965ce49`, used tree `2375d16ab2faaa10e30edc619431deda9d09cd64`. All candidate checks passed: CI and source validation, full self-check, docs, Helm/Kubernetes, Mypy/lint, invariants, Docker, Release, Gradient, Codex CI, and the Required Quality Gate. The 47-node acceptance check passed. The pre-commit finalizer and separate prepublication metadata guard were both ready. The strict hosted verifier ran with actual Administrator UID 0, preserved source identity, and passed strict audits and audit immutability without repair. The solo profile did not request an exhaustive matrix.

PR #2611 merged normally as `26f35f8221202cbbde5bd8c27cd67e9f00453bac`; its tree equals the candidate tree, with verified main `bd8ffa6a5fab52e677fa32d58fa902e0e965ce49` and candidate `15819c0a53b749b55b5773c827373ac90cdc92c0` as ordered parents. Post-merge CI, integrated source validation, strict Quality Gate, Invariants, Docker, Docs Deploy, and self-check passed. Forge Smoke was conditionally skipped.

PR #2610 had just integrated sequence 573's append-only evidence before this change: main `bd8ffa6a5fab52e677fa32d58fa902e0e965ce49`, tree `401a446a6f523f4ad1523838e707d901fd14f93e`, with source main `0a774ff5c9f79480e1ff7210dde81f0e26c9347c` and evidence candidate `04a03a5c219688009d5621cabcbb919499c1a119` as parents. Its exact-candidate checks and required gate passed, followed by green post-merge checks.

No production inference, model transition, or privileged operational mutation was run. Federation Health's current report remains a configured local log snapshot, not live telemetry.

Sequence: 574 (embodiment observation test-contract reconciliation)
