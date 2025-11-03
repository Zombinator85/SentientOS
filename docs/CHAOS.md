# Chaos Drills

The `scripts/chaos.sh` entrypoint exercises the primary failure paths for the autonomy runtime. Each flag can be combined so the
on-call operator can rehearse degraded states without impacting live data.

## Flags

| Flag | Purpose | Expected Signals |
| ---- | ------- | ---------------- |
| `--oracle-drop` | Forces `OracleGateway` into a degraded mode by triggering repeated failures. | `/admin/status` reports `mode=degraded`, `sos_oracle_rate_limited_total` increases only if the budget is exhausted, `glow/alerts/oracle_degraded.prom` flips to `1`. |
| `--critic-lag` | Saturates the critic semaphore by issuing more reviews than the concurrency limit. | `sos_critic_latency_ms_max` spikes, review payloads include `"timed_out": true`, and the dashboard event feed records the lag. |
| `--council-split` | Simulates a tie and a quorum miss to validate tie-breaker behaviour. | The returned payload includes `notes="tie_breaker:chair"`, metrics record quorum misses, and alerts warn when the miss ratio exceeds 20%. |
| `--curator-burst N` | Injects `N` synthetic memories to confirm curator back-pressure. | Memory curator backlog increases; rate-limit counters remain zero unless the daily budget is hit. |

Run drills locally with:

```bash
./scripts/chaos.sh --oracle-drop --critic-lag --council-split --curator-burst 25
```

The script prints a JSON payload containing the final `/admin/status` snapshot and the raw Prometheus metrics used by the
alerting toolchain. Operators can archive the payload for after-action reviews.

## E2E Verification

1. Execute the drill with the relevant flags.
2. Visit the operator dashboard to confirm degraded modules and rate-limit counters render clearly.
3. Run `./scripts/alerts_snapshot.sh` to ensure Prometheus snapshots capture the warnings.
4. Restore service health (e.g., rerun `make rehearse`) and verify the alerts clear.
