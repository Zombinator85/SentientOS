# Codex Workcell Pulse Contract

The Codex Workcell Pulse Contract is a deterministic, read-only catalog for naming, classifying, and bounding pressure signals that are already observable in a supplied Codex Workcell Health Snapshot. It answers: **“How are observed pressure signals named, classified, bounded, and prepared for future `/pulse` observation?”**

It does not answer whether a change may commit, whether PR metadata may be created, whether matrix proof passed as a new decision, whether artifacts are fresh as a new decision, whether a daemon should act, whether a watcher should run, whether federation consensus has been reached, whether a model is aligned, or whether reinforcement-learning training succeeded.

## Contract boundaries

The pulse contract is metadata-only and contract-only. It may define a static signal catalog and may optionally read one provided health snapshot JSON to summarize which catalog signals are observed. It must not run the health snapshot builder, tests, matrix, mypy, finalizer, PR metadata guard, lifecycle doctor, evidence index builder, appendix renderer, doctrine builder, docs, git, network, provider calls, shell commands, watchers, schedulers, daemon actions, model training, or reinforcement learning.

Missing optional health snapshot input is represented as `provided: false`. A provided but missing or invalid health snapshot fails cleanly before writing output.

## Difference from adjacent surfaces

- The architecture map defines component boundaries, flows, mounts, and future integration surfaces; the pulse contract only names pressure signals observed through metadata.
- The health snapshot answers **“What is currently observable about the workcell from supplied metadata artifacts?”** The pulse contract answers how those observed pressure signals are named, classified, bounded, and prepared for future `/pulse` observation.
- The matrix remains the proof runner and proof classifier. The pulse contract can label observed matrix pressure, but it does not rerun or reinterpret proof.
- The finalizer and PR metadata guard remain landing authorities. The pulse contract can label absent or rerun pressure from supplied metadata, but it does not authorize commits or PR creation.
- The lifecycle doctor, evidence index, evidence appendix, and doctrine map remain their own review surfaces. The pulse contract only records whether corresponding pressure categories are visible.
- Daemon repair remains future-only. The pulse contract is not a daemon trigger, alerting system, scheduler, or watcher.

## Signal naming and classification

Pulse signal IDs are stable snake-case identifiers such as `missing_matrix_evidence`, `matrix_required_failure_observed`, `stale_evidence_refresh_observed`, and `pulse_watch_not_active`. Each signal has a stable category and severity hint. Categories are `missing_input`, `proof_pressure`, `authority_pressure`, `freshness_pressure`, `provenance_pressure`, `doctrine_pressure`, `future_integration_pressure`, `daemon_boundary`, and `federation_boundary`. Severity hints are `info`, `watch`, `caution`, and `blocked_observation`.

Each catalog entry includes source health snapshot fields, an interpretation, a forbidden inference, a next observation recommendation, a non-authority boundary, and a reviewer summary. Observed signals are evidence labels only; they never trigger action.

## SentientOS mount alignment

- `/pulse`: pressure signal naming plus freshness, drift, timeout, and rerun observation.
- `/glow`: archived evidence and review surfaces that may provide observation context.
- `/ledger`: landed receipts that may provide history context.
- `/daemon`: a future repair recommendation consumer, not active in this contract.
- `/vow`: canonical constraints that bound interpretation and forbidden inference.

## Future activation requirements

Before this contract could become an active watcher, a separate future implementation would need an explicit scheduler or watch loop, explicit operator consent, explicit daemon boundary, explicit ledger/glow storage policy, explicit federation drift consensus rule, explicit finalizer/guard non-bypass invariant, tests proving no readiness authority, and docs marking active behavior. For this contract, every activation requirement is unmet and future-only.

## Non-authority posture

The contract is read-only, metadata-only, does not watch files, does not poll state, does not rerun commands, does not decide readiness, does not bypass the finalizer or PR metadata guard, does not authorize commit or PR creation, does not trigger daemons, does not schedule tasks, does not send alerts, does not train or modify models, and does not establish federation consensus.

## Daemon recommendation contract link

The daemon recommendation contract maps this contract's stable pulse signal IDs into review-only repair recommendation classes. It remains metadata-only and does not activate watching, scheduling, daemon action, readiness decisions, commits, PR metadata, ledger writes, memory mutation, model training, or federation consensus. See `docs/development/codex_workcell_daemon_recommendation_contract.md`.
## Memory contract boundary

The Codex Workcell Memory Contract may describe future `/ledger` and `/glow` metadata that `/pulse` could consume only after a separate watcher contract is activated; it is inactive here and does not watch, poll, or decide pressure.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) may represent a supplied pulse contract JSON as candidate `/ledger` and `/glow` review metadata. It does not activate pulse watching, poll state, decide pressure, or authorize landing.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) is inactive relative to `/pulse`: it may report candidate bundle consistency, but it does not watch stored history, poll state, emit pressure signals, schedule work, trigger daemon action, write `/ledger`, or archive `/glow`.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Vow boundary note

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) blocks pulse-as-action inference. Pulse signals remain inactive metadata unless a future explicit watcher/action contract is adopted.

## Vow alignment attestation note

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) may bind pulse contract reports to a supplied vow digest. Pulse metadata remains observational and the attestation does not watch, schedule, alert, or act.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) may describe future stored pulse history policy, but pulse contracts remain non-watching, non-scheduling, and non-executing metadata.

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
