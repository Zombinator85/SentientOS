# Codex Workcell Vow Alignment Attestation Bundle

The Codex Workcell Vow Alignment Attestation Bundle is a deterministic, metadata-only `/vow` review artifact. It reads a supplied Codex Workcell Vow Digest Boundary Contract JSON and optional workcell report JSON files, records raw-byte SHA-256 digests and byte sizes, and emits per-report alignment attestations bound to the supplied canonical vow digest.

It is not runtime authority. It does not activate memory, write `/ledger`, archive `/glow`, mutate memory, watch files, poll state, run commands, schedule tasks, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, create PRs, establish federation consensus, or train/modify models.

## Boundary contract vs. alignment attestation

The vow boundary contract defines canonical constraints, the canonical vow digest, forbidden inference catalog, report-alignment categories, future-only activation requirements, and non-authority posture. The vow alignment attestation consumes that contract as input and binds supplied report artifacts to its digest for reviewer inspection.

The attestation bundle does not recalculate authority, adopt the vow into runtime policy, or convert warnings/attestations into readiness. It only states whether supplied report metadata appears compatible with the supplied vow digest and forbidden inference boundary.

## Digest binding

For the required vow boundary contract JSON and every supplied optional report JSON, the CLI reads raw bytes, computes SHA-256, records byte size, and parses JSON object content. The supplied `canonical_vow_digest` and `canonical_vow_digest_algo` from the vow boundary contract are copied into every attestation record. If the supplied vow boundary contract lacks `canonical_vow_digest`, supplied report attestations fail rather than becoming authority.

## Constraint and forbidden inference assignment

Each supported report input has a stable mapping to applicable vow constraint IDs and forbidden inference IDs. Architecture reports bind to runtime-authority and hidden-authority constraints; health reports bind to health-is-not-readiness constraints; pulse reports bind to pulse-is-not-action constraints; daemon recommendation reports bind to recommendation-is-not-command constraints; memory surfaces bind to schema/candidate/verifier/preflight constraints that keep `/ledger`, `/glow`, readiness, and activation claims inactive.

These mappings are reviewer metadata only. Missing expected IDs are reported as coverage gaps against the supplied vow boundary contract catalog; gaps do not authorize activation or readiness.

## Attestation status is not readiness

Per-report statuses are limited to `attested`, `warning`, and `failed`. A supplied report fails when `metadata_only` is false, non-authority posture contains false values, active authority is detected, or the vow digest is absent. Missing `metadata_only` or missing non-authority posture warns unless active authority is detected.

No status grants readiness, finalizer bypass, PR metadata guard bypass, commit authority, PR creation authority, daemon execution, task creation, scheduling, ledger writing, glow archiving, memory mutation, federation consensus, or model training.

## Mount relationship

- `/vow`: canonical digest binding and forbidden inference attestation.
- `/ledger`: future consumer of vow-bounded write policy; inactive here.
- `/glow`: future consumer of vow-bounded archive policy; inactive here.
- `/pulse`: future consumer of vow-bounded observation history; inactive here.
- `/daemon`: future consumer of vow-bounded recommendation context; inactive here.

## Future activation requirements

Future activation remains unmet and inactive until separate contracts define explicit vow digest adoption policy, ledger writer implementation, glow archiver implementation, storage path policy, retention policy, digest verification policy, parent-chain validation policy, operator consent, finalizer/guard non-bypass invariant, pulse watcher contract, daemon action contract, federation drift consensus rule, tests proving no readiness authority, and docs marking active behavior.

## Non-authority posture

The bundle declares that it is read-only, metadata-only, attestation-only, and does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch files, poll state, rerun commands, decide readiness, bypass the finalizer, bypass the PR metadata guard, authorize commits, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) consumes vow boundary and attestation metadata as future-only storage adoption context; it does not make attestation an active writer, readiness decision, ledger write, or glow archive.

## Storage policy verifier boundary

See [Codex Workcell Storage Policy Verifier](codex_workcell_storage_policy_verifier.md) for the metadata-only structural verifier for storage policy contracts. Its verification status is not readiness authority and it does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, schedule tasks, or bypass finalizer/PR metadata guard requirements.
## Storage transaction dry-run planner boundary

The [Codex Workcell Storage Transaction Dry-Run Plan](codex_workcell_storage_transaction_plan.md) is the next metadata-only layer for supplied storage policy, candidate, verifier, and vow reports. It emits future `/ledger` and `/glow` would-write plans only; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, or create PRs.

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

## Storage operator consent request packet boundary

See [Codex Workcell Storage Operator Consent Request Packet](codex_workcell_storage_operator_consent_request_packet.md) for the deterministic metadata-only future request packet shape. The packet does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, create PRs, or establish federation consensus.

## Operator consent request packet verifier boundary

The [Codex workcell storage operator consent request packet verifier](codex_workcell_storage_operator_consent_request_packet_verifier.md) is a deterministic metadata-only structural check for request packet JSON. It does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide readiness, or replace finalizer/PR metadata guard authority.

## Storage operator consent response artifact boundary

The [Codex Workcell Storage Operator Consent Response Artifact Contract](codex_workcell_storage_operator_consent_response_contract.md) defines only the future response artifact schema for explicit `/ledger` and `/glow` consent. It does not create a response artifact, collect or imply consent, bind runtime authority, activate memory, write ledger entries, archive glow evidence, render UI, send messages, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, or create PRs.
