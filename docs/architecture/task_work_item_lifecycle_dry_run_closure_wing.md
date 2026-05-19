# Task Work Item Lifecycle Dry-Run Closure Wing

## Scope

This wing seals completed work-item lifecycle dry-run adapter outputs into a deterministic, reviewer-facing closure manifest. It is metadata-only and non-authoritative.

## Inputs

- normalized work-item packet JSON,
- lifecycle handoff plan JSON,
- lifecycle dry-run adapter result JSON.

## Output

A single metadata-only closure manifest containing compact IDs/digests/statuses/counts and contradiction/missing-metadata findings. Contradiction detection is primarily structured via explicit authority-claim flags, with legacy blocker/warning token scans retained as compatibility fallback signals. Optional explicit caller-supplied artifact write is supported.

## Boundaries

- Does **not** invoke intake, handoff planning, dry-run adapter, or workspace lifecycle orchestration.
- Does **not** execute, verify, close, rollback, or mutate workspace state.
- Does **not** perform network/provider/prompt calls, tracker mutations, branch/PR creation, scheduler action, or agent execution.
- Does **not** read workspace target files.

## Status classes

- `dry_run_closed_clean`
- `dry_run_closed_with_warnings`
- `dry_run_closed_blocked`
- `dry_run_closed_manual_review`
- `dry_run_closed_insufficient_metadata`
- `dry_run_closed_contradicted`
- `dry_run_closure_insufficient_evidence`

## Reviewer surfaces

- Module: `sentientos/work_item_dry_run_closure.py`
- CLI: `scripts/build_work_item_dry_run_closure.py`
- Tests: `tests/test_work_item_dry_run_closure.py`, `tests/test_build_work_item_dry_run_closure_script.py`

The reviewer proof bundle documents this capability and does not run the closure builder by default.

## Shared authority vocabulary producer contract

Work-item producer surfaces (intake packet, handoff plan, dry-run adapter result, and dry-run closure manifest) are contract-tested for authority-like field drift.

- Authority-looking field names are detected in tests using reviewer-only heuristics (for example `*_requested`, `*_invoked`, `*_performed`, plus tokens such as `authority`, `workspace`, `provider`, `network`, `scheduler`, `verification`, and `closure`).
- Every detected field must be either:
  1. a shared alias in `AUTHORITY_CLAIM_ALIASES` mapped to a canonical authority family, or
  2. listed in `NON_AUTHORITY_FIELD_ALLOWLIST` with explicit non-authority rationale.
- Unknown authority-looking fields fail deterministically so upstream producers cannot silently introduce unmapped authority semantics.
- Coverage walks nested mapping/list/tuple structures and reports deterministic dotted paths (for example `dry_run_result.lifecycle_summary.execution_performed` or `closure_manifest.artifacts[0].artifact_created`) so deeply nested drift is visible.
- Coverage includes representative serialized artifact payload shapes for intake packet, handoff plan, dry-run adapter artifact payload, and dry-run closure manifest payload.

### Safe update procedure for new producer fields

When adding a new authority-related producer field:

1. Add the exact field name to the correct canonical family in `AUTHORITY_CLAIM_ALIASES` (no fuzzy matching in runtime logic).
2. Ensure the field appears in representative producer output fixtures/tests.
3. Run the work-item authority tests to confirm deterministic coverage.

When adding a new non-authority field that happens to match heuristic tokens:

1. Add it to `NON_AUTHORITY_FIELD_ALLOWLIST` under the most specific category.
2. Include a compact rationale in code review/PR notes.
3. Keep runtime claim normalization unchanged unless the field actually conveys authority.
