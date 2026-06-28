# Codex Workcell Daemon Recommendation Contract

The Codex workcell daemon recommendation contract is a deterministic, metadata-only grammar for mapping existing Codex workcell pulse signal IDs into bounded repair recommendation classes. It is built by `scripts/build_codex_workcell_daemon_recommendation_contract.py` and implemented in `sentientos/codex_workcell_daemon_recommendation_contract.py`.

This contract differs from the pulse contract: the pulse contract names pressure signals, categories, and severity hints; this recommendation contract consumes those existing signal IDs and names review-only recommendation classes such as providing missing evidence, inspecting proof pressure, preserving a boundary, or requiring a future contract.

This contract also differs from actual daemon repair or daemon action. It does not watch files, poll state, run commands, create tasks, schedule work, send alerts, decide readiness, authorize commits, authorize PR metadata, write ledger entries, modify memory, train or modify models, or establish federation consensus. Applicable recommendations are observations for reviewers only.

## Recommendation mapping

The contract maps supplied pulse `observed_signal_summary.observed_signal_ids` to static recommendation IDs. Unknown observed signal IDs are preserved as unmatched. If no pulse contract JSON is supplied, observed and applicable recommendation lists remain empty and marked as not provided.

The recommendation catalog includes evidence-provision recommendations, proof/authority/freshness/provenance/doctrine inspection recommendations, future-integration documentation, boundary preservation, and future-contract requirements. Every source signal ID must already exist in the Codex workcell pulse contract.

## Input handling

The builder may read `--pulse-contract-json` and `--health-snapshot-json`. Each supplied input is read as raw bytes, hashed with SHA-256, byte-counted, and parsed as JSON object metadata. Missing, invalid, or non-object JSON fails cleanly before output is trusted. Omitted inputs are recorded with `provided: false` and no digest.

## SentientOS mount alignment

- `/daemon`: future repair recommendation consumer; inactive here.
- `/pulse`: source pressure signal categories and severity hints.
- `/glow`: future archive for observation surfaces and evidence context.
- `/ledger`: future receipt history context.
- `/vow`: canonical constraints bounding forbidden action and non-authority interpretation.

## Future activation requirements

All activation requirements are represented as future-only, unmet, and inactive. Active behavior would require a separate daemon implementation, explicit operator consent, command execution boundary, scheduler boundary, alerting boundary, task creation boundary, finalizer/guard non-bypass invariant, ledger/glow storage policy, pulse watcher contract, federation drift consensus rule, vow digest constraint check, tests proving no readiness authority, and docs marking active behavior.

## Non-authority posture

The contract is read-only and metadata-only. It cannot bypass the finalizer or PR metadata guard, cannot authorize commit or PR creation, cannot trigger daemon action, cannot create or schedule tasks, cannot send alerts, cannot watch or poll, cannot train or modify models, and cannot establish federation consensus.
## Memory contract boundary

The Codex Workcell Memory Contract defines future `/ledger` receipt-chain and `/glow` evidence-archive metadata for recommendation artifacts, but it does not write memory, archive evidence, trigger daemon action, or create authority.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) may represent a supplied daemon recommendation contract JSON as candidate memory review metadata only. The bundle does not trigger daemon action, schedule repair, create tasks, or convert recommendations into authority.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) verifies candidate memory bundle structure only. It is not a daemon recommendation consumer or executor and does not trigger daemon action, schedule work, create tasks, decide readiness, write `/ledger`, or archive `/glow`.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Vow boundary note

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) blocks recommendation-as-command and daemon-self-authorization inference. Daemon recommendations remain advisory metadata only.

## Vow alignment attestation note

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) may bind daemon recommendation reports to a supplied vow digest. Recommendations remain advisory metadata and the attestation does not command or trigger daemon action.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) is future storage metadata only; daemon recommendations remain advisory and cannot invoke storage, ledger, glow, or task actions.

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
