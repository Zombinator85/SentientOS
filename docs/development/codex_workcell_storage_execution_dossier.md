# Codex Workcell Storage Execution Readiness Dossier

The Codex Workcell Storage Execution Readiness Dossier is a deterministic, metadata-only review artifact for the future design of active storage. It reads supplied memory, vow, storage policy, transaction plan, and verifier reports; records raw-byte SHA-256 digests and byte sizes; inventories detected report identifiers and status fields; and summarizes whether the documentation prerequisites for designing an active `/ledger` writer and `/glow` archiver are present.

It is dossier-only. It does not activate memory, write ledger entries, archive glow evidence, mutate memory, watch files, poll state, run commands, schedule tasks, trigger daemon action, decide commit readiness, authorize PR metadata, create PRs, establish federation consensus, train models, or modify models.

## Transaction plan verifier vs execution dossier

The storage transaction plan verifier checks a supplied dry-run transaction plan structurally: planned mounts, planned paths, source digests, canonical vow context, parent-chain gaps, and dry-run non-authority posture. The execution dossier comes after those reports and inventories the broader evidence stack for reviewers who may later design an active writer. A `future_storage_design_dossier_complete` status is only a future-design dossier status; it is not finalizer readiness, PR metadata guard readiness, ledger authority, glow authority, daemon authority, storage activation, or permission to run an active writer.

## Evidence inventory

Each optional JSON input is read as raw bytes, hashed with SHA-256, measured by byte size, and parsed as a JSON object. Missing, invalid, or non-object JSON inputs fail cleanly in the CLI with exit code 2. Omitted optional inputs are recorded as not provided with null path, digest, and byte-size metadata. Supplied reports are inventoried by stable evidence roles: memory schema, memory candidate, memory verifier, memory preflight, vow boundary, vow attestation, storage policy, storage policy verifier, transaction plan, and transaction plan verifier.

## Future design completeness

The dossier is complete for future design review only when all required reports are supplied and verifier statuses that can be derived are successful. Missing reports make the dossier incomplete. Failed storage policy or transaction plan verifier statuses make the dossier failed. Active execution gaps remain blocking gaps in every case and never authorize storage.

## Active execution gaps

The dossier always records active writer implementation, operator consent, finalizer/guard runtime binding, storage path enforcement, retention enforcement, digest verification runtime, parent-chain runtime, pulse watcher contract, daemon action contract, and federation consensus as missing future-only gaps. `active_storage_allowed_now`, `execution_performed`, `writes_performed`, `archives_performed`, and `memory_mutation_performed` remain false.

## Reviewer URL hygiene

Reviewer URL hygiene is documented as a landing-task grep responsibility, not dossier runtime behavior. The dossier records the correct repository URL `https://github.com/Zombinator85/SentientOS.git` and the bad attribution URL expected to be absent, but it does not run grep or modify files.

## Mount alignment

- `/ledger`: future active storage target; no ledger write here.
- `/glow`: future active storage target; no archive write here.
- `/vow`: canonical digest context for execution boundaries.
- `/pulse`: future consumer of stored history; inactive here.
- `/daemon`: future consumer of pulse/recommendation context; inactive here.

## Future activation requirements

Future activation remains unmet and inactive until explicit active ledger writer implementation, active glow archiver implementation, storage path enforcement, retention enforcement, digest verification enforcement, parent-chain validation enforcement, operator consent, finalizer/guard runtime binding, pulse watcher contract, daemon action contract, federation drift consensus rule, tests proving no readiness authority, and docs marking active behavior are added by a separate authorized task.

## Non-authority posture

The dossier is read-only, metadata-only, and dossier-only. It does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch files, poll state, rerun commands, decide readiness, bypass finalizer, bypass PR metadata guard, authorize commit, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.
