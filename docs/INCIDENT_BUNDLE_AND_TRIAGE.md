# Incident Bundle and Triage

Use incident bundles to capture deterministic, bounded local-node triage artifacts.

## Generate bundle

```bash
make incident-bundle
# or
python scripts/incident_bundle.py --window 50 --json
```

## Bundle behavior

The bundle collector:
- runs deterministic replay verification (`forge_replay --verify`)
- snapshots latest constitution/governor/audit/pulse/federation/operator artifacts
- copies only latest file per glob surface
- includes bounded JSONL tails for high-volume streams
- emits `manifest.json` with file hashes and redaction/omission policy

No runtime state is mutated except new bundle artifacts and replay/status artifacts already defined by existing forge flow.

## Bundle layout

`glow/operators/incident_bundles/bundle_<ts>/`

- `manifest.json`
- `bundle_report.json`
- `included/...` (copied artifacts + bounded log tails)

## Triage checklist

1. Confirm `manifest_sha256` from `bundle_report.json`.
2. Validate `status.health_state` in `manifest.json`.
3. Inspect `included/glow/operators/current_restrictions.json`.
4. Inspect `included/glow/runtime/audit_trust_state.json` and continuation state.
5. Compare governance digest + trust-ledger peer summaries.
