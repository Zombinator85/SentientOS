# Maintenance task authority lease

The maintenance selector only decides that a candidate is eligible for scope admission. Selection is not permission. A caller-supplied operator grant is the standing authority ceiling, and a task lease is the immutable, task-specific subset derived from that ceiling.

The grant schema is `sentientos.maintenance_authority_grant:v1`; the lease schema is `sentientos.maintenance_task_authority_lease:v1`. Both use canonical JSON and SHA-256 sealing. The vocabulary is closed: `proposal_selection_only`, `filesystem_read`, `filesystem_write`, `documentation_edit`, `test_edit`, `code_edit`, `governance_edit`, `journal_read`, `validation_execute`, and `implementation_agent_session`. Commit, publication, host actuation, runtime adoption, and unrestricted secret access are intentionally absent.

Admission proves candidate kind, subject paths, forbidden patterns, authority classes, base SHA, file and changed-line budgets, implementation and validation time budgets, wall-clock ceiling, attempt ceiling, retry ceiling, grant generation, and explicit evaluation time are within the grant. Overbroad requests are rejected rather than clamped.

The admitted-scope digest binds candidate ID and revision, exact paths, authority, validation expectations, budgets, attempt and retry ceilings, time window, grant digest, and selector-policy digest. The task ID is derived by the maintenance-task journal from candidate reference, base SHA, candidate revision/contract digest, and admitted-scope digest. The lease ID is derived from that task ID and scope digest.

Lease artifacts live only under an explicit external state root at `maintenance_leases/<lease_id>.json`; they are immutable and reused only when exact bytes match. Admission appends `task_created` and `authority_lease_bound`, recovers after interruption, and starts zero attempts. Journal snapshots expose candidate revision, canonical candidate digest, selection digest, selector-policy digest, grant ID/digest, lease ID/digest, expiry, attempts, and retries.

Future action verification is metadata-only. It checks the lease artifact, active journal lease, task identity, revision, base SHA, expiry, revocation, paths, authority, budgets, attempts, and retries, then returns a decision without executing anything. Revocation appends `authority_lease_revoked`, preserves the lease file, and does not cancel or roll back work automatically.

Legacy operator-confirmed work-item and workspace packet paths remain compatibility surfaces. For the new maintenance loop, one lease replaces repeated routine approval relays; the operator still defines the standing grant and exceptional authority. The lease does not perform any admitted action. A future fake implementation-agent adapter will consume this lease as metadata before it proposes an attempt, but this surface does not launch the adapter.

No-effect posture: grant verification, admission, lease verification, action verification, inspection, and revocation do not launch agents, run task commands, edit repository source, run validation, invoke Git, create branches or commits, publish, perform host effects, adopt runtime capabilities, or read secrets. Permitted effects are immutable lease files, maintenance-task journal events, and caller-requested output artifacts under explicit external roots or output paths.
