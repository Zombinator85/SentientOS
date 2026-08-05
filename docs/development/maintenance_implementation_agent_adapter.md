# Maintenance implementation-agent adapter

The maintenance implementation-agent adapter coordinates implementation sessions; it does not perform implementation. It consumes an active maintenance-task authority lease, verifies a metadata-only implementation request, derives deterministic attempt/session identities, persists immutable session and result artifacts beneath an explicit external state root, and binds lifecycle events into the maintenance-task journal.

Schemas:

- Driver descriptor: `sentientos.maintenance_implementation_agent_driver:v1` with driver ID, closed driver kind, version, supported modes, effect class, external-session, polling, cancellation, recovery flags, and descriptor digest.
- Request: `sentientos.maintenance_implementation_agent_request:v1` binding task, lease, lease digest, candidate revision, canonical candidate digest, admitted scope, repository identity, exact base SHA, driver identity, attempt and corrective retry ordinals, objective, paths, validations, requested authority classes, time ceiling, deadline, optional opaque external instruction artifact digest, and constraints.
- Session: `sentientos.maintenance_implementation_agent_session:v1`, one immutable descriptor at `<state_root>/maintenance_agent_sessions/<session_id>.json`.
- Result: `sentientos.maintenance_implementation_agent_result:v1`, one immutable terminal artifact at `<state_root>/maintenance_agent_results/<session_id>.json`, bound to the terminal journal event ID and digest.
- Fake plan: `sentientos.maintenance_fake_agent_plan:v1`, a bounded deterministic list of `heartbeat`, `complete`, `fail`, or `interrupt` steps with exactly one terminal final step.

The only implemented driver kind is `fake_scripted`; `local_codex` is reserved and not implemented. The fake driver reports `synthetic_no_effect`; all effect booleans for repository mutation, command execution, validation, Git, publication, host effect, and runtime adoption remain false.

Starting a session is lease admission consumption, not implementation execution. `start_implementation_agent_session(...)` verifies the lease and action request, requires `implementation_agent_session`, derives the canonical attempt ID with the maintenance journal helper, derives a session reference ID with the journal helper, creates an immutable session descriptor, then records `attempt_started` and `agent_session_bound`. Exact retries reuse the same descriptor and missing journal events; conflicting bytes fail closed.

Polling is explicit. `poll_implementation_agent_session(...)` requires task ID, session ID, request, driver, and evaluation time. It emits at most one scripted step per call, records `attempt_heartbeat` for heartbeat steps, and writes an immutable terminal result before appending `implementation_completed`, `implementation_failed`, or `implementation_interrupted`. Timeout uses the caller-supplied evaluation time and the immutable deadline. Cancellation requires a non-empty reference, records an interrupted result, and does not revoke the lease, retry, rollback, or continue.

Interrupted-operation recovery is idempotent after descriptor persistence, attempt start, session binding, result persistence, or terminal journal recording. The lease, immutable descriptor/result artifact, and task journal are the recovery authority; no recovery packet is created.

No real Codex integration exists in this task. No prompt leaves the machine. No repository file is edited by adapter or fake-driver operations. No validation is run by the adapter. No commit or publication occurs. Fake completion is synthetic lifecycle proof only and is not acceptable as proof of repository change.
