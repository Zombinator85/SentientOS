# Immutable Manifest Contract (`/vow/immutable_manifest.json`)

`/vow/immutable_manifest.json` is the canonical immutability contract consumed by `scripts.audit_immutability_verifier`.

## Generation

Generate with:

```bash
python -m scripts.generate_immutable_manifest --manifest /vow/immutable_manifest.json
```

The generator is deterministic and writes stable JSON (`sort_keys=True`) with a canonical fingerprint (`manifest_sha256`) derived from canonicalized file entries.

## Contents

The manifest includes:

- `schema_version`
- `manifest_type`
- `generated_by`
- `tool_version`
- `captured_by` (git SHA when available)
- `canonical_serialization` policy
- `files` map containing deterministic entries keyed by normalized repo-relative path:
  - `sha256`
  - `size`
- `manifest_sha256` over canonicalized `files`

## Degraded mode

When inputs are missing, generation must be explicit:

- `--allow-missing-files` enables degraded mode.
- degraded output sets `degraded_mode.active=true` and records a reason code plus missing files.

No silent manifest omission is allowed.

## Verifier behavior

`audit_immutability_verifier` now fails by default when the manifest is missing.
Use `--allow-missing-manifest` only for intentionally degraded environments.
