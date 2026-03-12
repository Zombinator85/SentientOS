# Formal Specification + Model Checking Wing

This directory contains bounded, explicit formal state-machine specifications for the highest-stakes SentientOS control surfaces.

## Included models

- `runtime_governor`
- `audit_reanchor`
- `federated_governance`
- `pulse_trust_epoch`

## Runbook

```bash
python -m sentientos.ops verify formal
python -m sentientos.ops verify formal --json
python -m sentientos.ops verify formal --spec runtime_governor
python scripts/formal_check.py --repo-root . --json
```

Artifacts are written to `glow/formal/`:

- `formal_check_summary.json`
- `formal_check_manifest.json`

The formal wing is bounded for deterministic CI/dev execution and complements (does not replace) runtime simulation and baseline federation suites.
