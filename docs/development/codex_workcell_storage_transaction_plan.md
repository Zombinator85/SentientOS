# Codex Workcell Storage Transaction Dry-Run Plan

The Codex Workcell Storage Transaction Dry-Run Planner is a deterministic, metadata-only planner for future `/ledger` and `/glow` storage transactions. It reads supplied storage policy, storage policy verifier, memory candidate bundle, memory candidate verifier, vow boundary, and vow alignment reports, then emits would-write and would-archive plans without writing anything.

The planner is not a writer or archiver. It does not activate memory, write ledger entries, archive glow evidence, mutate memory, watch files, poll state, run commands, schedule tasks, trigger daemon action, decide readiness, authorize commit, authorize PR metadata, create PRs, establish federation consensus, or train or modify models.

## Policy, verifier, and transaction plan boundaries

- The [storage policy contract](codex_workcell_storage_policy_contract.md) defines future-only path, digest, retention, parent-chain, consent, and mount rules.
- The [storage policy verifier](codex_workcell_storage_policy_verifier.md) checks the supplied policy structure and confirms that active storage remains blocked.
- This transaction plan consumes those supplied reports plus candidate and vow reports to describe exact future `/ledger` and `/glow` operations an explicitly separate active writer would need to perform later.

A dry-run transaction plan is not readiness authority and cannot replace the finalizer, PR metadata guard, validation matrix, operator consent, or active writer implementation.

## Candidate records to planned transactions

Each `candidate_ledger_entries` item from the memory candidate bundle becomes one `ledger_write_candidate` plan with a deterministic transaction ID, source input ID, source artifact digest metadata, parent-chain context, canonical vow digest context, and `write_performed: false`.

Each `candidate_glow_items` item becomes one `glow_archive_candidate` plan with a deterministic transaction ID, source input ID, source digest metadata, related candidate ledger entry context, retention requirement, canonical vow digest context, and `archive_performed: false`.

## Planned path selection

The planner uses allowed path templates declared by the supplied storage policy. It prefers templates in this order:

1. `commit_sha`, when supplied;
2. `pr_number`, when supplied;
3. `canonical_vow_digest`, when available from CLI, vow boundary, or vow attestation.

If none of those values are available, `planned_path` is `null` and the transaction records a blocking path gap. The planner never constructs absolute host paths, network paths, provider-opaque paths, temp canonical paths, or hidden backdoor paths.

## Gaps and validations

The plan reports path validation, digest validation, parent-chain planning, vow alignment, and an aggregate transaction gap summary. Missing source digests, missing parent context, unverified storage policy, unverified candidate bundle, failed vow alignment, forbidden paths, missing operator consent, missing finalizer/guard runtime binding, and missing active writer implementation remain blocking gaps for any future active write.

Parent-chain context is planned but never written. Digest status is summarized but not enforced as an active storage operation. Vow alignment is checked for planning only and performs no vow adoption.

## Reviewer URL hygiene

The reviewer hygiene summary records that bad OpenAI-owned SentientOS repository attribution is expected to be absent and that the correct clone URL is `https://github.com/Zombinator85/SentientOS.git`. Repository grep validation remains part of the landing task, not runtime planner behavior, and legitimate OpenAI API/model/ChatGPT/Codex references remain outside this planner's authority.

## Mount alignment

- `/ledger`: dry-run transaction planning only; no ledger write.
- `/glow`: dry-run transaction planning only; no archive write.
- `/vow`: canonical digest context for transaction constraints.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.

## Future activation requirements

Future activation requires explicit active ledger writer implementation, active glow archiver implementation, storage path enforcement, retention enforcement, digest verification enforcement, parent-chain validation enforcement, operator consent, finalizer/guard runtime binding, pulse watcher contract, daemon action contract, federation drift consensus rule, tests proving no readiness authority, and docs marking active behavior. All are future-only, unmet, and inactive in this planner.

## Non-authority posture

The storage transaction plan is read-only, metadata-only, and dry-run-only. It does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch files, poll state, rerun commands, decide readiness, bypass finalizer, bypass PR metadata guard, authorize commit, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.

## Storage transaction plan verifier boundary

The [Codex Workcell Storage Transaction Plan Verifier](codex_workcell_storage_transaction_plan_verifier.md) is a deterministic metadata-only structural verifier for dry-run storage transaction plans. It checks planned `/ledger` and `/glow` transaction shape, paths, digests, parent-chain gaps, vow alignment context, transaction gaps, reviewer hygiene metadata, future activation requirements, and non-authority posture; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, create PRs, or establish federation consensus.
## Storage execution readiness dossier boundary

The [Codex Workcell Storage Execution Readiness Dossier](codex_workcell_storage_execution_dossier.md) may inventory this report as metadata-only evidence for future active-storage design. It does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, decide readiness, authorize PR metadata, or grant runtime storage authority.

## Storage execution dossier verifier boundary

See [Codex Workcell Storage Execution Dossier Verifier](codex_workcell_storage_execution_dossier_verifier.md) for the metadata-only structural verifier that checks dossier evidence inventory, inactive future activation requirements, active execution gaps, reviewer URL hygiene context, and non-authority posture without granting readiness, storage, ledger, glow, daemon, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority.

## Storage runtime authority boundary contract note

The [Codex Workcell Storage Runtime Authority Boundary Contract](codex_workcell_storage_runtime_authority_contract.md) records future-only runtime binding requirements for active `/ledger` and `/glow` storage. It is metadata-only and does not grant readiness, finalizer authority, PR metadata authority, runtime write authority, ledger writes, glow archives, daemon action, scheduling, memory mutation, or federation consensus.

## Storage runtime authority verifier boundary

See [Codex Workcell Storage Runtime Authority Boundary Verifier](codex_workcell_storage_runtime_authority_verifier.md) for the metadata-only structural verifier that checks the future-only runtime authority contract without granting readiness, binding runtime authority, writing `/ledger`, archiving `/glow`, mutating memory, scheduling work, triggering daemon action, or establishing federation consensus.

## Storage operator consent request boundary

See [Codex Workcell Storage Operator Consent Request Contract](codex_workcell_storage_operator_consent_contract.md) for the metadata-only future consent request shape. That contract does not collect consent, imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, or authorize PR metadata.

## Storage operator consent request verifier boundary

See [Codex Workcell Storage Operator Consent Request Verifier](codex_workcell_storage_operator_consent_verifier.md) for the deterministic metadata-only verifier for the future operator consent request shape. The verifier does not collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, or establish federation consensus.
