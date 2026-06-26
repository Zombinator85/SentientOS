# Codex Workcell Health Snapshot

The Codex Workcell Health Snapshot is a deterministic, metadata-only cockpit/vitals layer for the Codex developer-workflow workcell. It answers: **What is currently observable about the workcell from supplied metadata artifacts?** It reads optional JSON artifacts and renders a compact JSON snapshot plus optional Markdown for reviewers.

It is not authority. It does not run commands, create gates, schedule tasks, trigger daemons, authorize commits, authorize PR metadata, call providers, use the network, or train/modify models.

## Inputs and outputs

`scripts/build_codex_workcell_health_snapshot.py` accepts `--output` and optional `--markdown-output`, plus optional JSON inputs for architecture, matrix, pre-commit finalizer, PR-metadata finalizer, PR metadata guard, lifecycle summary, lifecycle doctor, evidence index, evidence appendix sidecar, and beneficial trait doctrine map.

The builder only reads paths supplied to those input flags. Missing optional inputs are recorded as not provided. A supplied path that is missing or invalid JSON fails cleanly before a successful snapshot is written.

## Difference from adjacent artifacts

- The Codex Workcell Architecture answers: **How do the workcell organs and flows fit together?**
- The health snapshot answers: **What is currently observable about the workcell from supplied metadata artifacts?**
- The review packet matrix remains proof-signal evidence; the snapshot only summarizes observed matrix fields.
- `codex_finalize_landing.py` remains commit/pr-metadata phase authority; the snapshot only displays provided finalizer statuses as observed evidence.
- `codex_pr_metadata_guard.py` remains PR metadata authority; the snapshot only displays the supplied guard status.
- The lifecycle doctor interprets lifecycle evidence; the snapshot summarizes the supplied doctor report without replacing it.
- The evidence index catalogs artifacts; the snapshot summarizes supplied catalog fields.
- The evidence appendix renders reviewer context; the snapshot can reference appendix sidecar provenance without verifying authority.
- The beneficial trait doctrine map explains doctrine posture; the snapshot summarizes that map as doctrine-only and not model training.

## SentientOS mount relationship

The snapshot renders a mount view for `/vow`, `/glow`, `/pulse`, `/daemon`, and `/ledger`. When architecture JSON is supplied, mount summaries are observed from the architecture map. Without architecture JSON, the snapshot uses static conceptual mount categories and marks them as not provided.

- `/vow`: doctrine and constraint observations.
- `/glow`: evidence memory and rendered review-surface observations.
- `/pulse`: stale-evidence, diagnostic, and pressure observations.
- `/daemon`: repair-recommendation context only, never daemon action.
- `/ledger`: receipt/provenance context only, never landing authority.

## Non-authority posture

The snapshot does not answer whether a change may commit, whether PR metadata may be created, whether matrix proof passed as a new decision, whether artifacts are fresh as a new decision, whether a daemon should act, whether federation consensus has been reached, whether a model is aligned, or whether reinforcement-learning training succeeded.

Its recommendations are phrased as observation recommendations only, such as supplying architecture JSON for fuller component/flow context or supplying appendix sidecar JSON for rendered-surface provenance.

## Pulse contract relationship

The Codex Workcell Health Snapshot answers what is currently observable from supplied metadata artifacts. The Codex Workcell Pulse Contract consumes an optional snapshot JSON only as input evidence and answers how observed pressure signals are named, classified, bounded, and prepared for future `/pulse` observation. It does not run this snapshot builder or decide readiness.

## Daemon recommendation contract boundary

Health snapshot metadata may be referenced by the daemon recommendation contract for digest and input-summary context, but recommendations are derived from supplied pulse contract observed signal IDs and remain observation-only. See `docs/development/codex_workcell_daemon_recommendation_contract.md`.
## Memory contract boundary

The Codex Workcell Memory Contract defines how health snapshots could be represented in future `/ledger` and `/glow` metadata, without writing ledger entries, archiving glow evidence, or changing snapshot authority.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) may represent a supplied health snapshot JSON as candidate memory metadata. This does not make the health snapshot a gate, readiness decision, ledger write, glow archive, or runtime authority.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) can inspect candidate records that reference supplied evidence artifacts. It does not observe live health, mutate memory, decide readiness, write `/ledger`, archive `/glow`, trigger daemons, schedule work, or create tasks.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Vow boundary note

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) blocks health-as-readiness inference. Health snapshots remain cockpit metadata and do not replace matrix, finalizer, guard, or operator authority.

## Vow alignment attestation note

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) may bind health snapshot reports to a supplied vow digest. Health alignment is reviewer metadata and does not decide readiness.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) can define future archival policy for health snapshots; health snapshots still do not decide readiness or write storage.

## Storage policy verifier boundary

See [Codex Workcell Storage Policy Verifier](codex_workcell_storage_policy_verifier.md) for the metadata-only structural verifier for storage policy contracts. Its verification status is not readiness authority and it does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, schedule tasks, or bypass finalizer/PR metadata guard requirements.
## Storage transaction dry-run planner boundary

The [Codex Workcell Storage Transaction Dry-Run Plan](codex_workcell_storage_transaction_plan.md) is the next metadata-only layer for supplied storage policy, candidate, verifier, and vow reports. It emits future `/ledger` and `/glow` would-write plans only; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, or create PRs.
