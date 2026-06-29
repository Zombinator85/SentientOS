# Codex Workcell Storage Policy Verifier

The Codex Workcell Storage Policy Verifier is a deterministic, metadata-only verifier for a supplied Codex Workcell Storage Policy Contract JSON. It reads raw bytes, records SHA-256 digests and byte sizes, parses JSON objects, and emits structural verification metadata for future `/ledger` and `/glow` storage policy.

It is not a writer, archiver, watcher, scheduler, executor, alerting system, daemon action, task creator, readiness decision, finalizer bypass, PR metadata authority, memory activation path, model trainer, or federation consensus mechanism.

## Contract vs verifier

The storage policy contract defines future path, retention, digest, parent-chain, and vow-bound adoption policy. The storage policy verifier checks whether a supplied contract structurally declares those policy elements. A verified status means only that the policy JSON shape passed deterministic structural checks; it does not authorize active storage, commit, PR metadata, ledger writes, glow archives, daemon action, or memory mutation.

## Structural checks

The verifier checks that the contract declares metadata-only and policy-only posture, no runtime authority, no ledger writer, no glow archiver, and `active_storage_allowed_now: false`. It also verifies required ledger record types, glow archive item types, digest policy IDs, parent-chain policy IDs, retention policy IDs, path scope policy IDs, inactive future activation requirements, and all-true non-authority posture flags.

Optional vow boundary, vow alignment, memory contract, and memory activation preflight reports are summarized as context only. The verifier does not run builders, run verifiers, run tests, poll state, watch files, or execute shell commands.

## Why verification status is not readiness authority

`storage_policy_verified`, `storage_policy_failed`, and `storage_policy_incomplete` describe storage-policy structure only. They are not matrix authority, finalizer authority, PR metadata guard authority, commit authority, ledger authority, glow authority, daemon authority, or permission to run an active writer.

## Mount alignment

- `/ledger`: storage policy verification only; no ledger write.
- `/glow`: storage policy verification only; no archive write.
- `/vow`: canonical digest context for future storage adoption.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse and recommendation context; inactive here.

## Reviewer URL hygiene

This task also corrected accidental public repository ownership attribution from the accidental OpenAI-owned SentientOS clone URL to `https://github.com/Zombinator85/SentientOS.git`. That documentation hygiene fix is separate from verifier runtime behavior. Legitimate OpenAI references for models, APIs, ChatGPT, Codex, papers, or compatibility remain outside this verifier's authority.

## Future activation requirements

Active storage still requires explicit ledger writer implementation, glow archiver implementation, storage path enforcement, retention enforcement, digest verification enforcement, parent-chain validation enforcement, operator consent, finalizer/guard runtime binding, pulse watcher contract, daemon action contract, federation drift consensus rule, tests proving no readiness authority, and docs marking active behavior. All are future-only and inactive here.

## Non-authority posture

The verifier is read-only, metadata-only, and verifier-only. It does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch files, poll state, rerun commands, decide readiness, bypass finalizer, bypass PR metadata guard, authorize commit, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.
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

## Storage operator consent response verifier boundary

The [Codex Workcell Storage Operator Consent Response Artifact Verifier](codex_workcell_storage_operator_consent_response_verifier.md) is a deterministic metadata-only structural verifier for the future response artifact contract. It creates no response artifact, collects or implies no consent, grants no readiness, storage, ledger, glow, daemon, federation, UI, message, scheduler, commit, PR metadata, or runtime authority, and leaves active storage blocked.

## Storage operator consent evidence dossier boundary

See [Codex Workcell Storage Operator Consent Evidence Dossier](codex_workcell_storage_operator_consent_evidence_dossier.md). The dossier inventories future consent-design evidence only; it does not present a request, collect a response or consent, imply approval, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide readiness, or authorize commit/PR metadata.
