# Sequence 553 — preserve explicit empty subprocess environments

`run_supervised(env={})` was silently converted to `env=None` by a truthiness check, causing the child to inherit the parent environment even when the caller explicitly requested an empty environment. The supervisor now distinguishes an omitted environment from an explicitly supplied mapping. A regression sets a parent-only sentinel and proves the child cannot read it when passed an empty mapping.

The regression failed on the verified parent by printing the inherited sentinel, then passed after the fix. The Required Quality Gate exact acceptance grew from 39 to 40 nodes, and its reconstruction and finalizer count bindings were updated consistently. All 10 supervisor tests and all 50 hosted workflow contract tests passed locally; compilation, strict Mypy for the changed module, and whitespace validation passed.

PR #2565 merged normally as `a18ae26a9cd5a0440d5e9a654cf45ab5245626ad`, tree `49f158f370927a75878de6a4492f08b7bab8cdb7`, with ordered parents `c898bcb4d8923b2c96ce307f5c49e2f7bf2e4aea` and `15173d47a45de1d2a8977c4448cba85b393146cf`. The exact-candidate Required Quality Gate, privileged finalizer, separate metadata guard, CI, Mypy, Docker, invariants, Release, Codex CI, and Gradient checks passed. Post-merge CI, QG, Docker, Docs Deploy, Nightly Self Check, invariants, and Codex CI passed on the exact merged main; Forge Smoke was skipped by its configured condition.

Latest verified source main: `a18ae26a9cd5a0440d5e9a654cf45ab5245626ad`, tree `49f158f370927a75878de6a4492f08b7bab8cdb7`
Latest construction segment: `work/construction/segments/0553-preserve-explicit-empty-subprocess-environments.md`
Sequence: 553 (verified merge reconciliation)

Next: make bounded subprocess pipe draining work on native Windows, where selectors cannot monitor anonymous pipes, while preserving timeout and platform-specific process-tree evidence.
