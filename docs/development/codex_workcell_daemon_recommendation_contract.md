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
