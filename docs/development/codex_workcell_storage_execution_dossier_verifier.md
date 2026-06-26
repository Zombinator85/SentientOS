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
