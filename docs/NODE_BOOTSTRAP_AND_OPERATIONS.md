# Node Bootstrap and Operations

## One-command bootstrap

Use the local bootstrap command to converge a fresh workspace into a deterministic node posture:

```bash
make node-bootstrap
```

Equivalent CLI:

```bash
python -m sentientos.ops node bootstrap --seed-minimal --json
# compatibility shim
python scripts/node_bootstrap.py --seed-minimal --json
```

Bootstrap phases:
1. Initialize runtime directories (`glow/runtime`, `glow/governor`, `glow/pulse_trust`, `glow/federation`, `glow/operators`, `pulse/audit`).
2. Optionally seed minimal bootstrap requirements (`vow/immutable_manifest.json`) when missing.
3. Compose and persist constitution surfaces.
4. Run explicit trust restoration + re-anchor flow if required.
5. Emit cockpit artifacts and bootstrap report.

All restoration/bootstrapping actions are append-only via `glow/operators/restoration_history.jsonl` and `glow/forge/restoration/*.json`.

## Operator cockpit surfaces

Bootstrap and health commands generate bounded deterministic artifacts under `glow/operators/`:

- `operator_summary.json`
- `operator_summary.md`
- `peer_health_summary.json`
- `current_restrictions.json`
- `restoration_history.jsonl`
- `bootstrap_report_*.json`

## Ongoing operations

### Health

```bash
make node-health
# or
python -m sentientos.ops node health --json
```

### Restore degraded/restricted posture

```bash
make node-restore
# or
python scripts/node_bootstrap.py --seed-minimal --reason operator_node_restore --json
```

### Constitution and forge surfaces

```bash
python -m sentientos.ops constitution json
python -m sentientos.ops forge status --json
python -m sentientos.ops forge replay --verify
```

## Exit codes

- `0`: healthy
- `1`: degraded
- `2`: restricted
- `3`: missing bootstrap requirements
