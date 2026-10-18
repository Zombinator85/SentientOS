# Sequence 405: reject symlinked CI artifact output roots

The exact merged main source tree `4cb880075654f30b5664a525a668f5ef44e98761` exposed one remaining edge in sequence 404's artifact staging helper: it bounded and validated source reports, but followed a pre-existing symlink at the output-directory path. Repository-controlled test code could pre-create that path and redirect staged artifacts outside the intended per-job temporary directory. The helper now fails closed when the output root is a symlink or a non-directory. Existing source containment, source SHA, freshness, deterministic ranking, and omission behavior are unchanged.

A regression creates an output-directory symlink to a separate directory, verifies a clear rejection, and proves the target remains empty. On a clean checkout carrying the exact GitHub main tree, the canonical runner completed 45/45 selected artifact-staging and workflow-contract tests with zero skips or failures. Focused mypy, compilation, diff checks, and pre-append strict custody of all 404 sequences passed. The local test wrapper commit is recorded separately from the verified remote source identity; its tree exactly matches main `5a97f4395f32f59febc51ad1eba589729ea13122` / `4cb880075654f30b5664a525a668f5ef44e98761`.

The exact-main post-merge Required Quality Gate, CI, Docker, Invariants, Docs Deploy, and Codex CI runs all succeeded. Its QG artifact independently binds strict privileged audit and immutability success plus 29/29 acceptance nodes to main SHA `5a97f4395f32f59febc51ad1eba589729ea13122`. Forge Smoke was skipped by the configured opt-in condition. The next scheduled Federation Health event on this exact main and the scheduled nightly executions remain pending; no manual run is substituted.

This increment changes only read-only artifact staging behavior and its tests. It grants no write permission, runtime authority, inference, provider invocation, or production effect. Hosted verification for this source candidate remains pending.

Latest construction segment: `work/construction/segments/0405-reject-symlink-artifact-output-root.md`
Latest segment SHA-256 is bound in the append-only construction index.
Sequence: 405 (local tests and source checks passed; hosted candidate verification pending)
