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


## Repository mutation custody

The default `sentientosd` maintenance loop does not stage files, create commits, mutate branches, push, or create pull requests. It may emit deterministic metadata-only repository mutation handoffs for already-approved explicit-path proposals; those handoffs require external operator/Codex landing review and do not authorize mutation. `updater.py` / `sentientos-updater` is treated as an explicit operator-invoked legacy utility, not daemon default behavior.

### Repository mutation custody v2 sealing

Repository mutation handoffs now use `repository-mutation-handoff.v2`. A ready v2
handoff is metadata-only and requires an approved proposal, an approval/ledger
reference, exact `approved_paths` / `approved_path_digests` set equality, a
lowercase SHA-256 approval digest for every approved file, and an
`approved_source_revision` that exactly matches the read-only observed revision
from `git rev-parse HEAD`. Missing approval references, missing digest data, or
unknown source revisions are incomplete; digest mismatches, revision mismatches,
unsafe paths, outside-repository evidence, and approved-path/digest set
mismatches are contradicted. v1 artifacts remain historical review metadata and
are not sufficient for v2 readiness.

The daemon writes runtime handoff artifacts outside the repository worktree. The
resolved root precedence is: explicit injection,
`SENTIENTOS_REPOSITORY_MUTATION_HANDOFF_ROOT`,
`LOCALAPPDATA/SentientOS/repository_mutation_handoffs` on Windows,
`XDG_STATE_HOME/sentientos/repository_mutation_handoffs`, then
`~/.local/state/sentientos/repository_mutation_handoffs`. Roots equal to or
contained in the repository, including `.git`, are refused. Handoff emission uses
atomic JSON writes and must not create `integration/repository_mutation_handoffs`
or dirty the repository worktree.

No unused Git mutation convenience helper remains. The daemon-facing API is a
repository-mutation handoff reader, not a commit-state API: it does not stage
files, create commits, mutate branches, push, create pull requests, mark
proposals committed, adopt proposals, invoke providers, assemble prompts, or
expand runtime authority. External Codex/operator landing controls, including
finalizer, matrix, supervisor, and PR metadata guard, remain required.
