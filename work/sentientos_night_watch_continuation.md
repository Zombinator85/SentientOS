# SentientOS construction campaign II continuation

Non-authorizing progress record. Construction code is **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remote checkpoint

GitHub Git-data publication advanced the branch to `5a81c5e3d1b24dfd4a898a2464b2e70d8d710f7f`, tree `aa03b314db293fd7c1f1ac2f128a05a86dd3be3d` (parent `5462623c355ea92569b89c6aa10d2825df3fa872`), using a compare-and-swap ref update. The commit was fetched by SHA and the branch-selected continuation file was reread after publication. The local historical Git checkout has a stale parent; local commit IDs are not remote commit identities.

## Construction added after that checkpoint

- Added `sentientos/platform_fcntl.py` as an import-safe facade for the POSIX lock dependency. On Windows, read-only recovery modules can import without substituting another lock primitive. Any requested `flock` fails with `ENOSYS`; wake-owner startup, successor-generation startup/handoff/config generation, and authority-continuity derivation refuse to proceed before their first effect.
- Routed every direct `fcntl` import in the statically traced 24-module successor-adoption import closure through the facade. Static source traversal now finds no direct `fcntl` import in that closure. This is not an executed Windows import test.
- Changed continuity policy and generation-manifest loaders, wake configuration and adoption loaders, and cadence-journal replay to use the existing explicit descriptor/handle-safe bounded reader. The cadence journal is limited to 16 MiB, 65,536 rows, and 65,536 bytes per row; replay validates digest lineage and canonical row bytes. Windows missing-file status is distinct for empty optional journals.
- The model-replacement campaign store now reconstructs its protocol/state through bounded Windows handle reads and validates canonical bytes. Campaign recovery no longer calls `experiment.run()` for an interrupted trial; it preserves the in-progress state as `interrupted_trial_preserved_not_replayed`. A read-only custody inspection exposes that incomplete state without an inference endpoint.
- Wake-daemon owner event replay is now bounded and digest/canonicality checked. Cadence rows enforce alternating intent/completion identity and bounded appends; owner evidence has its own retention cap. Inspection reports that a start record is not proof of current liveness.
- The post-adoption and model-replacement readers retained their preceding bounded, canonical, read-only behavior. This work does not make their writers or live transition effects Windows-capable.

## Verification and limits

Python compilation for changed modules, static import-closure inspection, and `git diff --check` passed. No tests, runtime execution, Windows execution, provider use, or production verification was performed. Windows lock behavior is designed to fail closed but has only been source-inspected and compiled on this host. Windows atomic writers, the model-replacement effect path, and broader cross-platform durable developmental-history publication remain unresolved.

## Next executable task

Trace the developmental-history and longitudinal self-model stores used by resident cognition for Windows read-only reconstruction, preserving single-writer POSIX publication. Then review the experiment store's exact interrupted-condition lineage so no separate caller can mistake a durable start for a completed run. Continue to keep model adoption and inference effects behind their existing independent owners.
