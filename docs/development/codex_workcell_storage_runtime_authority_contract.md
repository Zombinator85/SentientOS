# Codex Workcell Storage Runtime Authority Boundary Contract

The Codex Workcell Storage Runtime Authority Boundary Contract is a deterministic, metadata-only contract for future active `/ledger` and `/glow` storage work. It defines the runtime authority bindings that a later authorized implementation would need before any active storage behavior could exist.

It is contract-only. It does not activate memory, write ledger entries, archive glow evidence, mutate memory, watch files, poll state, run commands, schedule tasks, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, create PRs, establish federation consensus, train models, or modify models.

## Dossier/verifier vs runtime authority boundary

The storage execution dossier inventories the evidence stack for future active-storage design. The storage execution dossier verifier checks that dossier structurally and confirms that active execution gaps remain visible. This runtime authority boundary contract comes after them as a policy map of future runtime bindings; it does not verify the dossier, rerun any builder, rerun any verifier, or transform report status into authority.

A complete dossier, a passing dossier verifier, `ready_to_commit`, and `pr_metadata_guard_ready` are review and landing statuses only. They are not runtime write authority for `/ledger` or archive authority for `/glow`.

## Required future runtime bindings

Future active storage remains blocked until an authorized later task supplies explicit implementations and tests for:

- active ledger writer implementation;
- active glow archiver implementation;
- finalizer runtime binding implementation;
- PR metadata guard runtime binding implementation;
- explicit operator consent capture;
- storage path enforcement;
- retention enforcement;
- digest verification enforcement;
- parent-chain validation enforcement;
- pulse watcher contract;
- daemon action contract;
- federation drift consensus rule;
- tests proving no readiness authority;
- docs marking active behavior.

Every requirement is represented as future-only, unmet, and inactive in this contract.

## Finalizer and guard readiness are not write authority

The contract records that finalizer and PR metadata guard bindings are required for any future active storage design. It also records that finalizer `ready_to_commit` and PR metadata guard readiness are not runtime write authority. They control landing flow; they do not permit ledger writes, glow archives, daemon action, storage execution, or memory mutation.

## Operator consent is required and absent

Operator consent is explicitly required, absent, and not collected by this contract. Future consent must be explicit, scoped to `/ledger` and `/glow`, and must reference the canonical vow digest, storage policy, and transaction plan. This contract never infers consent from reports, tests, validation, matrix output, finalizer output, guard output, or PR metadata.

## Why active storage remains blocked

Active storage remains blocked because the active writer implementation, operator consent, finalizer/guard runtime binding, storage path enforcement, retention enforcement, digest verification runtime, parent-chain runtime, pulse watcher contract, daemon action contract, and federation consensus are all absent. The contract preserves those gap IDs as blocking future-only gaps.

## Not a writer or archiver

The contract is read-only and metadata-only. It can render JSON and Markdown artifacts for review, but those artifacts do not write `/ledger`, archive `/glow`, alter memory, watch paths, poll state, schedule work, create tasks, trigger daemons, establish consensus, or train models.

## Reviewer URL hygiene

Reviewer URL hygiene remains a landing-task grep responsibility. The contract records the correct repository URL `https://github.com/Zombinator85/SentientOS.git` and the bad attribution URL expected to be absent, but it does not run grep, modify files, or make hygiene a runtime behavior.

## SentientOS mount alignment

- `/ledger`: future runtime storage target; no ledger write here.
- `/glow`: future runtime archive target; no archive write here.
- `/vow`: canonical digest context required for runtime authority boundaries.
- `/pulse`: future watcher boundary; inactive here.
- `/daemon`: future action boundary; inactive here.

## Non-authority posture

The storage runtime authority boundary contract is read-only, metadata-only, and contract-only. It does not bind runtime authority, activate memory, write ledger entries, archive glow evidence, modify memory, watch files, poll state, rerun commands, decide readiness, bypass finalizer, bypass PR metadata guard, authorize commits, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.

## Storage runtime authority verifier boundary

See [Codex Workcell Storage Runtime Authority Boundary Verifier](codex_workcell_storage_runtime_authority_verifier.md) for the metadata-only structural verifier that checks the future-only runtime authority contract without granting readiness, binding runtime authority, writing `/ledger`, archiving `/glow`, mutating memory, scheduling work, triggering daemon action, or establishing federation consensus.
