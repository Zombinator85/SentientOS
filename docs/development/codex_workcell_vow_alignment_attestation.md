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
