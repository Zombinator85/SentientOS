# Maintenance Task Journal

The maintenance task journal is the canonical durable memory for future bounded repository-maintenance orchestration. It records task lifecycle facts in one append-only, tamper-evident event stream and derives snapshots by deterministic replay. It does **not** create a closed maintenance loop by itself.

## Authority posture

The journal has state-recording authority only. It does not choose candidates, launch Codex or another implementation agent, export prompts, call providers, access the network, run validation, execute subprocesses, run Git, stage, commit, push, publish, mutate repository source, actuate the host, retry work, schedule work, or adopt Genesis/runtime capabilities.

## Journal versus snapshot authority

The JSONL journal is authoritative. Each line is one canonical `sentientos.maintenance_task_event:v1` object. A `sentientos.maintenance_task_snapshot:v1` object is a cache or view that must be reproducible byte-for-byte from the journal plus an explicit evaluation time for time-relative fields such as lease expiry.

## Identity

A task ID is derived from caller-supplied canonical inputs: an opaque candidate reference, base repository SHA, normalized objective or task-contract digest, and admitted-scope digest. The journal does not infer candidate semantics from prose and does not define candidate selection.

Attempt, authority-lease, agent-session-reference, validation-reference, commit-reference, and publication-reference IDs are scoped deterministic digests. Retry uses a new attempt ID under the same task ID and cannot widen the recorded authority scope.

## Event chain

Every event binds schema version, event ID, task ID, sequence number, event type, previous-event digest, canonical payload, recorded timestamp, writer identity, optional repository SHA, and its own SHA-256 digest. Canonical JSON uses sorted keys and compact separators. Replay detects byte mutation, payload mutation, reordering, deletion, insertion, sequence errors, previous-digest errors, digest mismatches, and conflicting duplicate event IDs.

Timestamps and filesystem modification times are evidence only; they are not lifecycle authority.

## Lifecycle and transitions

The closed event vocabulary is: `task_created`, `authority_lease_bound`, `authority_lease_revoked`, `attempt_started`, `attempt_heartbeat`, `agent_session_bound`, `implementation_completed`, `implementation_failed`, `implementation_interrupted`, `validation_started`, `validation_passed`, `validation_failed`, `ready_to_commit_recorded`, `commit_recorded`, `publication_started`, `publication_succeeded`, `publication_failed`, `recovery_started`, `recovery_completed`, `task_blocked`, `task_cancelled`, and `task_closed`.

The reducer enforces explicit fail-closed transition law: a task must exist before attempts; attempts need an active lease; only one active lease and one active attempt are allowed; terminal attempts cannot receive heartbeats; validation success requires successful implementation; commit readiness requires passed validation; commit recording requires readiness; publication success requires a commit; closure cannot occur with an active attempt; closed or cancelled tasks cannot return to active state; recovery records cannot rewrite prior events.

## Idempotency and corruption

Appending the exact same canonical event twice returns `event_already_recorded`. Reusing an event ID with different bytes returns `event_conflict`. Illegal lifecycle edges return `transition_rejected` with stable reason codes. Replaying the same journal produces the same snapshot.

Replay reports `journal_ready`, `journal_tail_incomplete`, `journal_chain_broken`, `journal_record_invalid`, `journal_sequence_invalid`, or `journal_digest_mismatch`. A partial final record preserves earlier valid history; corruption in the middle fails closed. This task never truncates, compacts, repairs, or deletes damaged history.

## Concurrency and storage custody

Journal files live under an explicit external state root, outside the mutable repository worktree and outside `.git`. The writer takes an exclusive file lock, assigns the next stable sequence under the lock, appends one JSONL record, flushes, fsyncs the file, and fsyncs the containing directory before reporting success. Snapshot materialization uses atomic replacement and remains derived state.

The state-root guard rejects repository roots, descendants of the repository, `.git`, descendants of `.git`, symlink escapes back into the repository, non-directories, symlinked state files, and unexpected state-file identity/type changes during a write.

## Future references

A future candidate selector can supply an opaque candidate reference and admitted-scope digest to derive the task ID. A future implementation-agent adapter can bind only an agent-session reference. A future validation controller can record validation outcomes. Future commit, publication, and recovery custody can record references and outcomes here, but those components must hold their own explicit authority and must not treat journal events as permission to execute effects.
