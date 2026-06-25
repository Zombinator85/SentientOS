# Codex Workcell Memory Candidate Bundle

The Codex Workcell Memory Candidate Bundle is a deterministic, metadata-only review artifact. It reads only supplied JSON artifacts, records raw-byte SHA-256 digests and byte sizes, and renders candidate `/ledger` receipt entries plus candidate `/glow` archive items for reviewer inspection.

It is staging only. It does not write ledger entries, archive glow records, mutate memory, watch files, poll state, schedule work, trigger daemon action, create tasks, send alerts, decide readiness, authorize commits, authorize PR metadata, establish federation consensus, or train/modify models.

## Memory contract vs. candidate bundle

The [Codex Workcell Memory Contract](codex_workcell_memory_contract.md) defines future metadata schemas, record families, archive item families, source artifact alignment, mount alignment, and activation requirements for `/ledger` and `/glow` surfaces. The candidate bundle consumes an optional already-built memory contract JSON plus optional evidence artifacts and renders concrete candidate records that show what future receipt/archive metadata could look like.

If no memory contract JSON is supplied, the bundle uses the module's static fallback mappings. Those fallback mappings are schema-review metadata only and do not become storage policy or authority.

## Candidate ledger entries vs. actual ledger writes

Candidate ledger entries are deterministic JSON objects with `candidate_only: true` and `no_write_performed: true`. They include the source input id, source digest, byte size, candidate record type, optional discoverable commit/PR/status metadata, and explicit forbidden inference text.

A candidate ledger entry is not an actual `/ledger` write. It does not create a receipt chain, verify a parent chain, seal a commit, approve a PR, satisfy validation, or make evidence fresh. Active ledger behavior would require a separate ledger writer implementation, storage path policy, retention policy, digest verification policy, parent-chain validation policy, operator consent, finalizer/guard non-bypass invariant, tests proving no readiness authority, and docs marking active behavior.

## Candidate glow items vs. actual glow archiving

Candidate glow items are deterministic JSON objects with `candidate_only: true` and `no_archive_performed: true`. They include the source path, source digest, byte size, archive item type, optional related candidate ledger id, review surface, memory scope, authority boundary, and forbidden inference.

A candidate glow item is not an actual `/glow` archive record. It does not copy files, persist evidence, decide retention, disclose artifacts, activate a watcher, mutate memory, or train models. Active glow archiving would require a separate archiver implementation and explicit storage, retention, digest verification, operator consent, and documentation controls.

## How supplied artifacts become candidate records

The builder accepts optional JSON inputs for the memory contract, architecture map, health snapshot, pulse contract, daemon recommendation contract, matrix report, pre-commit finalizer, PR metadata finalizer, PR metadata guard, evidence index, appendix sidecar, and doctrine map. For every supplied input it reads raw bytes, computes SHA-256, records byte size, parses JSON as an object, and fails cleanly if the file is missing, invalid JSON, or non-object JSON.

Only supplied artifacts produce candidate records. Omitted inputs remain `provided: false` with null path, digest, and byte size. The builder does not run artifact builders, tests, matrix lanes, finalizers, guard commands, docs commands, git, shell commands, providers, network calls, watchers, or daemons.

## Review-only source artifact map

The source artifact map links each supplied input id to its candidate ledger entry ids and candidate glow item ids. This map supports reviewer traceability from source artifact bytes to candidate records. It is not a provenance seal, proof result, readiness decision, storage manifest, archive inventory, or federation consensus record.

## SentientOS mount relation

- `/ledger`: candidate receipt entries only; no ledger write.
- `/glow`: candidate archive records only; no archive write.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.
- `/vow`: canonical constraints bounding candidate interpretation and forbidden inference.

## Future activation requirements

All activation requirements are represented as future-only, unmet, and inactive: explicit ledger writer implementation, explicit glow archiver implementation, explicit storage path policy, explicit retention policy, explicit digest verification policy, explicit parent-chain validation policy, explicit operator consent, explicit finalizer/guard non-bypass invariant, explicit pulse watcher contract, explicit daemon action contract, explicit federation drift consensus rule, explicit vow digest constraint check, tests proving no readiness authority, and docs marking active behavior.

## Non-authority posture

The memory candidate bundle is read-only, metadata-only, and candidate-only. It does not write ledger, archive glow, modify memory, watch files, poll state, rerun commands, decide readiness, bypass the finalizer, bypass the PR metadata guard, authorize commit, authorize PR creation, trigger a daemon, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) can inspect a supplied candidate bundle for structural consistency and optional memory-contract type alignment. Its verification status is bundle-structure metadata only; it does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize commit/PR metadata, trigger daemons, create tasks, schedule work, alert, or establish federation consensus.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Vow boundary note

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) blocks candidate-as-write inference. Candidate bundle records remain staged metadata only, not `/ledger` entries or `/glow` archives.

## Vow alignment attestation note

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) may bind candidate bundle reports to a supplied vow digest. Candidate records remain metadata only and the attestation does not write `/ledger` or archive `/glow`.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) names future `/ledger` and `/glow` path policy for candidate records, but candidate bundles remain unwritten metadata.

## Storage policy verifier boundary

See [Codex Workcell Storage Policy Verifier](codex_workcell_storage_policy_verifier.md) for the metadata-only structural verifier for storage policy contracts. Its verification status is not readiness authority and it does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, schedule tasks, or bypass finalizer/PR metadata guard requirements.
