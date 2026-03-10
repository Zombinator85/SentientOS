# Health State Interpretation

SentientOS health surfaces converge on the following states:

- `healthy`: constitution healthy, integrity `ok`, runtime data healthy.
- `degraded`: constitution/forge indicate constrained posture or warning-grade trust/integrity pressure.
- `restricted`: explicit restricted posture (audit trust degradation, compromise response, or restricted runtime posture).
- `missing`: bootstrap requirements not present (for example immutable manifest or required constitutional artifacts).

## Unified commands

```bash
python scripts/node_health.py --json
python scripts/node_bootstrap.py --json
python scripts/system_constitution.py --json
python scripts/forge_status.py --json
```

`node_health` and `node_bootstrap` are the operator-facing canonical health classifiers.

## Operator interpretation guidance

- `healthy`: normal operation; continue periodic `forge_status` and replay verification.
- `degraded`: bounded operation allowed; prioritize replay verification and restoration checks.
- `restricted`: privileged actions should be halted or tightly controlled; run restoration flow and attach an incident bundle.
- `missing`: run node bootstrap with seeding enabled and re-check health.
