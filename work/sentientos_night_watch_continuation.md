# SentientOS construction campaign II continuation

Non-authorizing progress record. Construction code is **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remote checkpoint

GitHub Git-data publication advanced the branch to `290070f2b31acad0806adb0f30a022bb0bc900ba`, tree `0e667ae93f2747d99fce720152f3271a69850b56` (parent `be1efa3c835b5e7bb3584fe31e25d51f2e01c718`), using a compare-and-swap ref update. The commit was fetched by SHA and the branch-selected continuation file was reread after publication. The local historical Git checkout has a stale parent; local commit IDs are not remote commit identities.

## Construction added after that checkpoint

- Added `sentientos/platform_fcntl.py` as an import-safe facade for the POSIX lock dependency. On Windows, read-only recovery modules can import without substituting another lock primitive. Any requested `flock` fails with `ENOSYS`; wake-owner startup, successor-generation startup/handoff/config generation, and authority-continuity derivation refuse to proceed before their first effect.
- Routed every direct `fcntl` import in the statically traced 24-module successor-adoption import closure through the facade. Static source traversal now finds no direct `fcntl` import in that closure. This is not an executed Windows import test.
- Changed continuity policy and generation-manifest loaders, wake configuration and adoption loaders, and cadence-journal replay to use the existing explicit descriptor/handle-safe bounded reader. The cadence journal is limited to 16 MiB, 65,536 rows, and 65,536 bytes per row; replay validates digest lineage and canonical row bytes. Windows missing-file status is distinct for empty optional journals.
- The model-replacement campaign store now reconstructs its protocol/state through bounded Windows handle reads and validates canonical bytes. Campaign recovery no longer calls `experiment.run()` for an interrupted trial; it preserves the in-progress state as `interrupted_trial_preserved_not_replayed`. A read-only custody inspection exposes that incomplete state without an inference endpoint.
- Wake-daemon owner event replay is now bounded and digest/canonicality checked. Cadence rows enforce alternating intent/completion identity and bounded appends; owner evidence has its own retention cap. Inspection reports that a start record is not proof of current liveness.
- The durable epistemic owner can verify existing Windows custody without creating directories; all record publication fails closed on Windows until an equivalent atomic writer is available. Epistemic rows, resident cognition state/observation rows, and longitudinal-self-model history rows now reject noncanonical bytes during recovery. Resident cognition declines enabled execution on platforms where its state/observation publication path is not supported, before invoking the model.
- Developmental-history writeback can read and verify bounded canonical record custody on Windows but refuses new record/receipt publication there. Recovery cannot turn a missing receipt into a durable success on that platform. POSIX record recovery also enforces aggregate retention bytes.
- Developmental-history-intervention protocols/runs now have bounded canonical descriptor/handle reads and identity/digest reconstruction. Publication is POSIX-only; resident cognition already gates the operation before inference where publication is unsupported.
- Runtime admission custody now has a 4 MiB / bounded-row ledger reader with canonical serialization, duplicate identity/sequence rejection, and revocation-to-admission binding checks. Snapshot publication fails closed outside POSIX. The daemon's registered invocation receipt cache uses bounded handle-safe recovery, rejects malformed/noncanonical selections, and refuses unsupported-platform publication.
- The post-adoption and model-replacement readers retained their preceding bounded, canonical, read-only behavior. This work does not make their writers or live transition effects Windows-capable.

## Verification and limits

Python compilation for changed modules, static import-closure inspection, and `git diff --check` passed. No tests, runtime execution, Windows execution, provider use, or production verification was performed. Windows lock behavior is designed to fail closed but has only been source-inspected and compiled on this host. Windows atomic writers, the model-replacement effect path, and broader cross-platform durable developmental-history publication remain unresolved.

## Next executable task

Trace the software and cognitive-model transition custody composed by daemon startup, including transition journals and the post-exec readiness boundary. Keep Windows read-only inspection separate from replacement, process-start, grant issuance, or model invocation when durable mutation support is missing. Then follow any remaining source-backed causal integration gap.
