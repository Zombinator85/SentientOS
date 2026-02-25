# Attestation Framework

`sentientos/attestation.py` is the shared substrate for signed artifact flows used by rollups and strategic signatures.

## What it is

- One canonical JSON encoding (`sort_keys`, compact separators, UTF-8, trailing newline).
- Shared envelope hashing helpers for chained signature envelopes.
- Shared `VerifyResult` and verify-policy parsing (`warn` vs `enforce`, `last-N`, enable flags).
- Shared witness publishing interface with deterministic outcomes for:
  - disabled backend,
  - mutation disallowed,
  - repo dirty,
  - publish success/failure.

## How to enable

Strategic signing and verification controls remain in `docs/STRATEGIC_SIGNING.md`.
Rollup signing controls remain in `sentientos/signed_rollups.py` environment settings.

## Artifacts

- Strategic signatures: `glow/forge/strategic/signatures/`
- Rollup signatures: `glow/forge/rollups/*/signatures/`
- Strategic witness status: `glow/federation/strategic_witness_status.json`
- Optional file witness streams (backend=`file`) for strategic and rollup witness publication.

## Failure shape

Attestation failures stay deterministic and machine-parsable (`*_mismatch`, `signature_invalid`, publish `skipped_*`, etc.), with unchanged legacy wrappers like `verify_latest` preserved for callers.

See also: [STRATEGIC_SIGNING.md](./STRATEGIC_SIGNING.md).
