# Control-Plane Authority Map (Current Sensitive Scope)

This map reflects the implemented kernel-mediated sensitive boundaries in the current runtime scope.

| Authority class | Typical requester/source | Required phase(s) | Primary delegate checks | Execution owner | Audit output path |
| --- | --- | --- | --- | --- | --- |
| `proposal_evaluation` | `sentientosd` / `genesis_forge` maintenance loop | `maintenance` | runtime governor (`control_plane_task`), proof-budget governor (when provided), startup mediation | `GenesisForge.expand`, `IntegrityDaemon.guard` | `glow/control_plane/kernel_decisions.jsonl` |
| `proposal_adoption` | `genesis_forge` candidate promotion | `maintenance` | runtime governor (`amendment_apply`) | `AdoptionRite.promote` via `kernel.admit_and_execute` | `glow/control_plane/kernel_decisions.jsonl` |
| `manifest_or_identity_mutation` | `genesis_forge` lineage bind, operator manifest regeneration CLI | `maintenance` | runtime governor (`amendment_apply`) | `SpecBinder.integrate`, `scripts/generate_immutable_manifest.py` | `glow/control_plane/kernel_decisions.jsonl` |
| `repair` | `codex_healer` runtime remediation path | `runtime` | runtime governor (`repair_action`) | `RepairSynthesizer.apply` | `glow/control_plane/kernel_decisions.jsonl` |
| `daemon_restart` | `codex_healer` restart repairs | `runtime` | runtime governor (`restart_daemon`) | `RepairEnvironment.restart_daemon` via repair synthesis | `glow/control_plane/kernel_decisions.jsonl` |
| `federated_control` | federation pulse ingestion (`pulse_federation`) | `runtime` | runtime governor (`federated_control`), federation origin + denial metadata checks | pulse federation handlers after admission | `glow/control_plane/kernel_decisions.jsonl` |
| `spec_amendment` | `sentientosd` spec amender cycle | `maintenance` | runtime governor (`control_plane_task`) | `SpecAmender.cycle` | `glow/control_plane/kernel_decisions.jsonl` |
| `privileged_operator_control` | operator quarantine-clear CLI | `maintenance` | runtime governor (`control_plane_task`) + explicit gate disposition | `scripts/quarantine_clear.py` post-check clear path | `glow/control_plane/kernel_decisions.jsonl` |

Notes:
- Kernel decisions emit normalized provenance fields (`actor_source`, `authority_class`, `lifecycle_phase`, `delegate_checks_consulted`, `final_disposition`, `reason_codes`, `correlation_id`).
- Deny/defer/quarantine outcomes return before side-effect execution for `admit_and_execute` paths and guarded CLI mutation paths.
