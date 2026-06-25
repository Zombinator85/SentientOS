# Codex Workcell Memory Activation Preflight

The Codex Workcell Memory Activation Preflight is a deterministic, metadata-only report for future `/ledger` and `/glow` activation design. It reads a supplied memory contract JSON, memory candidate bundle JSON, and memory candidate verifier JSON; records raw-byte input summaries; and reports which prerequisite conditions are visible before any future writer could be designed or run.

It is not an activation mechanism. It does not write ledger entries, archive glow evidence, mutate memory, watch files, poll state, run commands, schedule work, trigger daemon action, create tasks, send alerts, train or modify models, establish federation consensus, decide commit readiness, authorize PR metadata, or create PRs.

## Ladder position

- The memory contract defines future `/ledger` receipt schemas and `/glow` archive schemas.
- The memory candidate bundle stages candidate ledger receipt entries and glow archive records from supplied artifacts without writing memory.
- The memory candidate verifier checks candidate bundle structure without writing ledger entries, archiving glow evidence, mutating memory, or creating authority.
- The activation preflight reviews the three supplied reports and makes future activation gaps explicit while remaining metadata-only and inactive.

## Preflight status is not permission

`activation_preflight_status` is a future-design status only. Even `activation_prerequisites_satisfied_for_future_design` does not authorize an active writer, commit, PR metadata, matrix bypass, finalizer bypass, ledger write, glow archive, daemon action, task creation, model update, or federation action.

## Future-only activation gaps

The report intentionally keeps active memory writing blocked. Operator consent, writer implementation, storage policy, federation consensus, and vow digest boundary checks remain expected blocking gaps for actual activation, not failures of the metadata-only preflight.

## Mount alignment

- `/ledger`: preflight only; no ledger write.
- `/glow`: preflight only; no archive write.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.
- `/vow`: canonical constraints bounding activation interpretation and forbidden inference.

## Future activation requirements

All requirements are represented as future-only, unmet, and inactive: explicit ledger writer implementation, explicit glow archiver implementation, storage and retention policy, digest and parent-chain validation policy, operator consent, finalizer/guard non-bypass invariant, pulse watcher contract, daemon action contract, federation drift consensus rule, vow digest constraint check, tests proving no readiness authority, and docs marking active behavior.

## Non-authority posture

The preflight declares that it is read-only, metadata-only, preflight-only, and does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch or poll files, rerun commands, decide readiness, bypass finalizer or PR metadata guard, authorize commit or PR creation, trigger daemon action, create or schedule tasks, send alerts, train or modify models, or establish federation consensus.

## Vow boundary contract link

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) is the future `/vow` constraint digest surface referenced by this preflight. It blocks preflight-as-activation inference while remaining metadata-only and inactive.

## Vow alignment attestation note

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) may attest that activation preflight metadata is bound to a supplied vow digest. That attestation is not activation and does not authorize memory writers, watchers, daemons, or readiness.
## Storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) fills the storage path, retention, digest, and parent-chain policy descriptions as metadata only; activation preflight remains inactive and active storage remains blocked.
