# Schema Policy

## When to bump `schema_version`
- Bump when changing required keys, semantics, or shape for emitted artifacts.
- Do not bump for additive optional fields that old readers can ignore safely.

## How to add an adapter
1. Add/update latest and minimum versions in `sentientos/schema_registry.py`.
2. Add a pure deterministic adapter in `ADAPTERS` keyed by `(schema_name, from_version)`.
3. Adapters must transform one version step at a time (`vN -> vN+1`).
4. Add/update tests to prove old payloads normalize to latest.

## Reader behavior
- Readers use upgrade-on-read normalization.
- Old files are never rewritten by normalization.
- If schema is too old, return/raise `schema_too_old:<schema_name>:<version>`.

## Stable keys
These keys must remain present across all versions:
- `schema_version`
- Artifact identity (`*_id` where applicable)
- Artifact timestamp (`created_at` or `generated_at`)
- Core status/decision field (`status`, `final_decision`, etc.)
