# Daemon Endurance + Chaos Validation Wing

This wing extends `lab federation` with deterministic, bounded-duration endurance scenarios that run real daemonized nodes and inject staged faults over time.

## How this differs from daemon parity

- Daemon parity confirms existing live scenarios work in daemon mode.
- Endurance adds **time-phased**, **seed-driven**, **bounded** chaos to validate recovery and convergence behavior under sustained pressure.
- Endurance writes a dedicated artifact tree under `glow/lab/endurance/`.

## Endurance scenarios

- `daemon_endurance_steady_state`
- `daemon_restart_storm_recovery`
- `daemon_reanchor_recovery_chain`
- `daemon_digest_mismatch_containment`
- `daemon_epoch_rotation_propagation`
- `daemon_pressure_fairness_endurance`

Each scenario defines:

- deterministic phase timeline (`at_s` offsets)
- deterministic seed-dependent schedule ordering
- bounded runtime window (`duration_s`)
- explicit expected outcomes for quorum/reanchor/epoch/fairness/health behavior

## Fault scheduling and execution

Deterministic scheduler behavior:

- explicit action sequence number
- bounded `offset_s` within runtime window
- target expansion (`all` or node-specific)
- each applied action logged to `scenario_injection_log.jsonl`

Fault families include:

- timed restart storms
- digest mismatch injection + cleanup
- epoch rotate + propagate
- replay duplication bursts
- pressure escalation + normalize
- noisy-subject fairness pressure
- re-anchor continuation chains

## Optional heavier execution modes

Single endurance scenario:

```bash
python -m sentientos.ops lab federation --scenario daemon_endurance_steady_state --mode daemon --runtime-s 4 --json
```

Run full bounded endurance suite:

```bash
python -m sentientos.ops lab federation --endurance-suite --mode daemon --seed 42 --json
make federation-lab-endurance MODE=daemon SEED=42
```

This mode is optional and not part of the default fast path.

## Out of scope

- true unbounded soak runs
- cross-host WAN fault domains
- architecture redesign of trust/governor/operator/runtime stack
