# SentientOS Live Commit Safety Interlock

The live commit safety interlock is a deterministic, metadata-only checkpoint that
sits after the live memory commit dry-run adapter and before any future real live
memory commit adapter. It evaluates explicit dry-run packet evidence,
execution-gate packet evidence, and interlock candidates to decide whether a
future live-memory commit adapter may be considered later.

## Public API

`sentientos/live_commit_safety_interlock.py` exposes these records:

- `LiveCommitSafetyInterlockPolicy`
- `LiveCommitSafetyInterlockInput`
- `LiveCommitSafetyInterlockCandidate`
- `LiveCommitSafetyInterlockFinding`
- `LiveCommitSafetyInterlockPrecondition`
- `LiveCommitSafetyInterlockSafetyNote`
- `LiveCommitSafetyInterlockRecord`
- `LiveCommitSafetyInterlockPacket`
- `LiveCommitSafetyInterlockReport`
- `LiveCommitSafetyInterlockResult`

The main entry point is `evaluate_live_commit_safety_interlock(payload, policy)`.
It returns deterministic JSON-compatible result dictionaries and SHA-256 digests.

## CLI

`scripts/build_live_commit_safety_interlock.py` supports:

- `build-default`
- `evaluate --input JSON [--output JSON] [--summary]`
- `validate [--input JSON]`
- `summarize --input JSON`
- `inspect-fixture --fixtures-dir PATH --fixture-name NAME`

The CLI exits nonzero for blocked, invalid, or failed statuses. The library does
not launch subprocesses, call providers, call remote services, write live memory,
delete files, mutate indexes, execute commits, or execute dry-run evidence as a
commit.

## Candidate and decision behavior

Allowed candidate types are metadata-only interlock candidates for AI capsule,
human summary, dual capsule, protect receipt, merge receipt, tomb archive, tomb
deferred, operator review, noop, and mixed diagnostics. Candidate evidence must
reference matching dry-run and execution-gate packet digests and decisions.

The interlock can produce these future-adapter consideration decisions:

- `live_commit_adapter_consideration_eligible`
- `live_commit_adapter_consideration_eligible_with_warnings`
- `live_commit_adapter_consideration_deferred_for_operator_review`
- `live_commit_adapter_consideration_rejected`
- `live_commit_adapter_consideration_blocked`
- `live_commit_adapter_consideration_noop`

Eligible outputs still do not perform a live commit. They only record that a
future adapter may be prepared later, with final live commit review still
required.

## Safety preconditions and previews

Non-noop candidates require operation, receipt, rollback, and safety
precondition metadata by default. Safety preconditions must match the dry-run
packet digest, execution-gate packet digest, operation preview digest, receipt
preview digest, rollback preview digest, and scope digest.

Operation previews must remain hypothetical and unapplied. Receipt previews must
remain hypothetical and must not claim receipt emission. Rollback previews must
remain hypothetical and must not claim rollback was applied.

## Default-deny non-authority boundaries

Every successful packet repeats explicit invariants:

- the interlock is not a memory write, deletion, index mutation, capsule
  persistence, prompt assembly, execution, live commit, truth, policy, authority,
  or consent;
- the interlock does not execute actions and does not disclose externally;
- live memory writes, live memory deletions, index mutation, capsule persistence,
  prompt materialization, external disclosure, and remote services remain
  disabled;
- default-deny live commit posture remains true;
- a future commit adapter and final live commit review remain required;
- dry-run adapter, execution gate, receipt preview, rollback preview, and safety
  preconditions remain required.

## Blocker behavior

The interlock blocks missing or invalid dry-run packets, missing or invalid
execution-gate packets, missing or invalid interlock candidates, non-ready
upstream decisions, digest mismatches, decision mismatches, missing previews,
missing or mismatched safety preconditions, hard claims of live writes/deletes,
index mutation, capsule persistence, tomb completion, prompt materialization,
action execution, external disclosure, authority/policy/truth/consent smuggling,
raw/private/media/secret/prompt payload leakage, and scope mismatch. Mixed-scope
diagnostics warn only when policy explicitly allows them.

Operator review cannot override hard blockers. Successful outputs include a
forbidden-next-step ledger covering live writes/deletes/purges, prompt assembly,
live context retrieval, action ingress, dry-run-as-commit execution,
interlock-as-commit execution, upstream bypasses, and external disclosure.

## Fixtures and proof integration

Metadata-only fixtures live under
`tests/fixtures/live_commit_safety_interlock/`. They cover all candidate types,
warning/diagnostic output, mixed packets, and every hard blocker. The capability
is registered as `live_commit_safety_interlock`, included in the reviewer proof
bundle as `live_commit_safety_interlock_capability`, and wired into the work-item
review packet matrix.
