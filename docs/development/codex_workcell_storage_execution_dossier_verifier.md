# Codex Workcell Storage Execution Dossier Verifier

The Codex workcell storage execution dossier verifier is a deterministic,
metadata-only verifier for a supplied storage execution readiness dossier JSON.
It checks whether the dossier preserves its evidence inventory, future-design
status, active execution gaps, reviewer hygiene context, and non-authority
posture. It emits a structural verification report only.

The storage execution dossier inventories supplied memory, vow, and storage
reports and summarizes future active-storage design completeness. The dossier
verifier is one layer higher: it verifies that the dossier itself remains
self-consistent and does not convert future-design status into execution
readiness or runtime authority.

The verifier checks that the dossier declares `metadata_only`, `dossier_only`,
`execution_not_performed`, no writes, no archives, and no memory mutation. It
also checks that evidence inventory, readiness evidence summary, active
execution gap summary, execution prerequisite results, future activation
requirements, and non-authority posture are present and structurally aligned.
When optional source reports are supplied, they are parsed as context and their
raw-byte SHA-256 digest and byte size are recorded; the verifier does not run
any builders or subordinate verifiers.

Verifier status is dossier-structure status only. It is not commit readiness,
PR readiness, matrix authority, finalizer authority, PR metadata authority,
ledger authority, glow authority, daemon authority, storage activation, or
permission to run an active writer. Active execution gaps must remain visible
and blocking so reviewers can see that active ledger writing, glow archiving,
storage path enforcement, retention enforcement, digest enforcement, parent
chain validation, operator consent, finalizer/guard runtime binding, pulse
watcher contracts, daemon action contracts, and federation drift consensus are
still future-only.

The verifier is not a writer or archiver. It does not activate memory, write
ledger entries, archive glow evidence, mutate memory, watch files, poll state,
run commands, schedule tasks, create tasks, send alerts, trigger daemon action,
train or modify models, establish federation consensus, authorize commits,
authorize PR metadata, or create PRs.

Reviewer URL hygiene remains separate from runtime behavior. The verifier
reports the expected bad and corrected repository URLs as metadata so reviewers
know what the landing task must grep for, but repository grep validation is
performed by the landing task, not by the verifier.

SentientOS mount alignment:

- `/ledger`: dossier verification only; no ledger write.
- `/glow`: dossier verification only; no archive write.
- `/vow`: canonical digest context for execution boundaries.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.

Future activation remains unmet and inactive until separate explicit contracts,
implementations, tests, and docs authorize active behavior. Required future
activation requirements include explicit active ledger writer implementation,
explicit active glow archiver implementation, storage path enforcement,
retention enforcement, digest verification enforcement, parent-chain validation
enforcement, operator consent, finalizer/guard runtime binding, pulse watcher
contract, daemon action contract, federation drift consensus rule, tests proving
no readiness authority, and docs marking active behavior.

The non-authority posture requires all verifier flags to remain present and
true, including read-only, metadata-only, verifier-only, no memory activation,
no ledger write, no glow archive, no memory modification, no watchers, no
polling, no rerun commands, no readiness decision, no finalizer/guard bypass,
no commit or PR authority, no daemon trigger, no task creation or scheduling,
no alerts, no model training, and no federation consensus.

## Storage runtime authority boundary contract note

The [Codex Workcell Storage Runtime Authority Boundary Contract](codex_workcell_storage_runtime_authority_contract.md) records future-only runtime binding requirements for active `/ledger` and `/glow` storage. It is metadata-only and does not grant readiness, finalizer authority, PR metadata authority, runtime write authority, ledger writes, glow archives, daemon action, scheduling, memory mutation, or federation consensus.

## Storage runtime authority verifier boundary

See [Codex Workcell Storage Runtime Authority Boundary Verifier](codex_workcell_storage_runtime_authority_verifier.md) for the metadata-only structural verifier that checks the future-only runtime authority contract without granting readiness, binding runtime authority, writing `/ledger`, archiving `/glow`, mutating memory, scheduling work, triggering daemon action, or establishing federation consensus.

## Storage operator consent request boundary

See [Codex Workcell Storage Operator Consent Request Contract](codex_workcell_storage_operator_consent_contract.md) for the metadata-only future consent request shape. That contract does not collect consent, imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, or authorize PR metadata.

## Storage operator consent request verifier boundary

See [Codex Workcell Storage Operator Consent Request Verifier](codex_workcell_storage_operator_consent_verifier.md) for the deterministic metadata-only verifier for the future operator consent request shape. The verifier does not collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, or establish federation consensus.

## Storage operator consent request packet boundary

See [Codex Workcell Storage Operator Consent Request Packet](codex_workcell_storage_operator_consent_request_packet.md) for the deterministic metadata-only future request packet shape. The packet does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, create PRs, or establish federation consensus.

## Operator consent request packet verifier boundary

The [Codex workcell storage operator consent request packet verifier](codex_workcell_storage_operator_consent_request_packet_verifier.md) is a deterministic metadata-only structural check for request packet JSON. It does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide readiness, or replace finalizer/PR metadata guard authority.

## Storage operator consent response artifact boundary

The [Codex Workcell Storage Operator Consent Response Artifact Contract](codex_workcell_storage_operator_consent_response_contract.md) defines only the future response artifact schema for explicit `/ledger` and `/glow` consent. It does not create a response artifact, collect or imply consent, bind runtime authority, activate memory, write ledger entries, archive glow evidence, render UI, send messages, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, or create PRs.
