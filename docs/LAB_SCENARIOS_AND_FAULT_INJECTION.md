# Lab Scenarios and Fault Injection

Live lab scenarios are deterministic by `seed` for node identity, ports, topology, run path, and bounded fault schedule.

## Fault adapters (live)

The lab includes explicit process/runtime fault adapters:

- peer digest mismatch (`peer_digest_mismatch`)
- trust epoch mismatch (`trust_epoch_mismatch`)
- replay duplication storm (`replay_duplication`)
- forced audit-chain break (`audit_chain_break`)
- forced re-anchor continuation (`force_reanchor`)
- governor pressure escalation (`governor_pressure_escalation`)
- local safety override (`local_safety_override`)
- restart storm (`restart_storm`)

All injections are written to `scenario_injection_log.jsonl` and preserved in artifact manifest outputs.

## Scenario mapping

- `healthy_3node`: no injections
- `quorum_failure`: digest + epoch mismatch on separate peers
- `replay_storm`: bounded duplicate replay writes
- `reanchor_continuation`: break then re-anchor continuation on one node
- `pressure_local_safety`: pressure escalation + safety dominance + restart storm
