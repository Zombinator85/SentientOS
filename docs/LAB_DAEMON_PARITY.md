# Live Federation Lab Daemon Parity

## Meaning of daemon parity

Daemon parity means live federation lab nodes run the actual SentientOS runtime daemon entrypoint (currently `scripts/orchestrator_daemon.py`) instead of only bounded worker heartbeat loops.

This enables process-level lifecycle evidence, restart supervision, and daemon-path observability while preserving deterministic orchestration and bounded artifacts.

## What is now parity-complete

- Deterministic per-node runtime roots (`glow/lab/federation/<run_id>/nodes/node-XX`)
- Deterministic per-node identity and port assignment
- Explicit runtime mode routing (`worker` / `daemon` / `auto`)
- Process lifecycle supervision (start/stop/restart/timeout transitions)
- Bounded watchdog behavior on shutdown/restart
- Explicit fault injection logging and scenario timeline logging
- Incident bundle + replay integration in daemon mode

## Oracle assertions strengthened for daemon mode

The live oracle now includes daemon runtime checks such as:

- all node daemons reached runtime start state (`runtime_boot_behavior`)
- quorum scenario behavior still enforced (`quorum_behavior`)
- re-anchor continuation still recognized (`continuation_behavior`)
- replay storm remains bounded (`replay_behavior`)
- local safety still dominates under pressure (`local_safety_behavior`)

## Remaining limitations

- Current daemon parity uses local orchestrator daemon entrypoint; it does not yet include long-haul, high-duration multi-host endurance runs.
- Heavy, expensive full-duration daemon integration tests are intentionally not part of default CI.
- Worker mode remains available and may still be preferred for quick local smoke checks.

## Operator interpretation guidance

When triaging a daemon-mode run:

1. Check `run_summary.json` mode fields (`runtime_mode_requested`, `runtime_mode_resolved`).
2. Inspect `process_transitions.jsonl` for per-node lifecycle state transitions and PID continuity.
3. Correlate `scenario_injection_log.jsonl` entries with `event_timeline.json` ordering.
4. Use `artifact_manifest.json` for immutable file/hash inventory.
5. If emitted, inspect incident bundles and replay verification results in `run_summary.json`.
