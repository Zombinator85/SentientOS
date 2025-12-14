# Autonomous Operations

`autonomous_ops.py` provides a minimal self-monitoring loop. It scans emotion, EEG, haptic and bio logs for anomalies and automatically creates experiments and reflex rules when stress spikes are detected.

Generated rules are logged to `logs/reflections/reflex_audit.jsonl` and all actions dispatched autonomously are written to `logs/autonomous_calls.jsonl` via `api.actuator.auto_call`.

Run the loop with:

```bash
python autonomous_ops.py --interval 30
```

The loop continuously prunes ineffective rules and stores offsets in `logs/autonomous_state.json` so it only processes new events. The included example detects simultaneous high stress and beta EEG and starts a `calm_down` workflow.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
