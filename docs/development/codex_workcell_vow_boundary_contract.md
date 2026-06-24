# Codex Workcell Vow Digest Boundary Contract

The Codex Workcell Vow Digest Boundary Contract is a deterministic, metadata-only `/vow` report. It publishes canonical constraint records, a stable SHA-256 digest over those constraints, forbidden inference mappings, and optional alignment summaries for supplied workcell reports.

It is not active authority. It does not activate memory, write `/ledger`, archive `/glow`, mutate memory, watch files, poll state, run commands, schedule tasks, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, create PRs, establish federation consensus, or train/modify models.

## How it differs from adjacent workcell surfaces

- Architecture maps describe the workcell shape and future surfaces; the vow boundary says which authority claims must not be inferred from that shape.
- Health snapshots render supplied evidence as cockpit/vitals metadata; the vow boundary blocks health-as-readiness inference.
- Pulse contracts define pressure signal names; the vow boundary blocks pulse-as-action inference.
- Daemon recommendation contracts describe advisory repair recommendations; the vow boundary blocks recommendation-as-command and daemon self-authorization inference.
- Memory contracts define future `/ledger` and `/glow` schemas; the vow boundary blocks schema-as-write inference.
- Memory candidate bundles stage candidate records; the vow boundary blocks candidate-as-ledger-write or candidate-as-glow-archive inference.
- Memory candidate verifiers inspect candidate structure; the vow boundary blocks verification-as-readiness inference.
- Memory activation preflight exposes future activation prerequisites and gaps; the vow boundary blocks preflight-as-activation inference.

## Canonical constraint digest

The contract sorts canonical constraint records by `constraint_id`, serializes only those records with `json.dumps(sort_keys=True, separators=(",", ":"))`, and computes a SHA-256 digest over the UTF-8 bytes. Input paths, input report content, timestamps, runtime environment details, and alignment summaries are excluded from the canonical vow digest.

That digest is stable review metadata only. A matching digest does not authorize writers, daemons, runtime action, finalizer bypass, PR metadata guard bypass, commit, PR creation, federation adoption, or memory activation.

## Forbidden inference catalog

The forbidden inference catalog maps workcell surfaces to claims that must remain false. It blocks claims such as architecture implying runtime authority, health implying readiness, pulse implying action, daemon recommendation implying command, memory contract implying storage write, candidate bundle implying `/ledger` or `/glow` writes, verifier implying readiness, activation preflight implying activation, evidence indexes or appendices implying authority, doctrine maps implying model training, provenance digests implying trust without source authority, and future integrations implying active behavior.

## Report alignment summaries

When optional report JSON files are supplied, the CLI reads raw bytes, records SHA-256 digest and byte size, parses JSON object content, and emits alignment metadata. Omitted inputs are `not_supplied`. Supplied reports missing `metadata_only` warn rather than fail. Supplied reports with false non-authority posture, active writer flags, active daemon flags, scheduler flags, or other active authority indicators fail alignment.

Alignment is not readiness authority. It is a reviewer-facing boundary check only.

## Mount relationship

- `/vow`: canonical constraint digest and forbidden inference boundary.
- `/ledger`: future consumer of vow-bounded write policy; inactive here.
- `/glow`: future consumer of vow-bounded archive policy; inactive here.
- `/pulse`: future consumer of vow-bounded observation history; inactive here.
- `/daemon`: future consumer of vow-bounded recommendation context; inactive here.

## Future activation requirements

Future active memory work remains unmet and inactive until separate contracts define explicit vow digest adoption policy, ledger writer implementation, glow archiver implementation, storage path policy, retention policy, digest verification policy, parent-chain validation policy, operator consent, finalizer/guard non-bypass invariant, pulse watcher contract, daemon action contract, federation drift consensus rule, tests proving no readiness authority, and docs marking active behavior.

## Non-authority posture

The vow boundary contract declares that it is read-only, metadata-only, contract-only, and does not activate memory, write `/ledger`, archive `/glow`, modify memory, watch files, poll state, rerun commands, decide readiness, bypass the finalizer, bypass the PR metadata guard, authorize commits, authorize PR creation, trigger daemons, create tasks, schedule tasks, send alerts, train or modify models, or establish federation consensus.
