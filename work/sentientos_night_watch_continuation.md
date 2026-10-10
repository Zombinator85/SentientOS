# SentientOS construction campaign II continuation

Non-authorizing progress record. Construction code is **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remote checkpoint

Before this continuation, the branch was verified at `5462623c355ea92569b89c6aa10d2825df3fa872`, tree `d3b14cd6ea5d13a224946d32bdc2d164ee3be4d2` (the prior checkpoint commit was `84dd6d2aef1785fc06123a7662b68cecb9288a81`). The local historical Git checkout has a stale parent; its commit IDs are not the remote commit identities. New edits in this continuation are not published until a subsequent remote branch update is verified.

## Construction added after that checkpoint

- Added `sentientos/platform_fcntl.py` as an import-safe facade for the POSIX lock dependency. On Windows, read-only recovery modules can import without substituting another lock primitive. Any requested `flock` fails with `ENOSYS`; wake-owner startup, successor-generation startup/handoff/config generation, and authority-continuity derivation refuse to proceed before their first effect.
- Routed every direct `fcntl` import in the statically traced 24-module successor-adoption import closure through the facade. Static source traversal now finds no direct `fcntl` import in that closure. This is not an executed Windows import test.
- Changed continuity policy and generation-manifest loaders, wake configuration and adoption loaders, and cadence-journal replay to use the existing explicit descriptor/handle-safe bounded reader. The cadence journal is limited to 16 MiB, 65,536 rows, and 65,536 bytes per row; replay validates digest lineage and canonical row bytes. Windows missing-file status is distinct for empty optional journals.
- The post-adoption and model-replacement readers retained their preceding bounded, canonical, read-only behavior. This work does not make their writers or live transition effects Windows-capable.

## Verification and limits

Python compilation for changed modules, static import-closure inspection, and `git diff --check` passed. No tests, runtime execution, Windows execution, provider use, or production verification was performed. Windows lock behavior is designed to fail closed but has only been source-inspected and compiled on this host. Windows atomic writers, the model-replacement effect path, and broader cross-platform durable developmental-history publication remain unresolved.

## Next executable task

Trace `developmental_model_replacement_campaign.py` and its callers to separate bounded read-only transition recovery from POSIX lock/publication effects. Make its recovery/import path cross-platform only where existing immutable custody supports it; preserve fail-closed transition and model-serving behavior without adding an adoption mechanism. Then inspect the adjacent wake-daemon owner receipt recovery path for remaining unbounded state reads.
