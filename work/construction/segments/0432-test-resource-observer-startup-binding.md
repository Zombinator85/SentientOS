# Sequence 432 — Bind resource-observer startup to explicit read-only selection

**Construction status: source candidate pending hosted verification.** The daemon's opt-in production-chat resource observer configuration was inline in startup. That left the disabled/incomplete/configured decision without a focused regression test, even though the downstream owner and resource-to-cognition lifecycle were covered.

Sequence 432 extracts the selector decision into a private startup helper and tests its trust boundary. With neither selector, the result is disabled and the installation registry is not opened. With incomplete selectors, startup returns an invalid configuration without opening the registry. With both selectors, the helper obtains only a read-only installation view and reports `source_not_yet_observed`; configuration alone does not claim verification. The first bundle read still occurs during the daemon tick, and an absent bundle fails closed.

This is a bounded refactor and regression test. It does not enable configuration, create or mutate installation custody, grant allocation/effect authority, or claim production use.

Source base: verified main `3d6e050e7caf903614027e666792314470177b66`, tree `96ef34fcc02391609458c439e66a7464dadd6dd9`. Local verification: Python compilation, direct helper assertions for disabled, incomplete, and read-only configured states, and `git diff --check` passed. Focused pytest collection was blocked by the repository's canonical test-install guard (exit 4); no local pytest pass is claimed. Exact-candidate hosted CI, strict quality gate, and invariants are pending.
