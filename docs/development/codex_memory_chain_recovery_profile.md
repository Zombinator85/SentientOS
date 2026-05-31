# Codex Memory-Chain Recovery Profile

This profile defines compact recovery behavior for partial failures in recurring memory-chain metadata-verification tasks. It is for repairing incomplete or failed landings without repeating the full subsystem prompt, while preserving the same safety, authority, audit, finalizer, PR metadata guard, fixture-root, and clean-tree requirements.

## When to use this recovery profile

Use this profile when a memory-chain metadata-verification task partially failed, left task-owned docs/tests/fixtures/artifacts inconsistent, failed a validation lane, produced stale evidence, or needs deterministic cleanup before landing. It applies to recovery of review-only, dry-run, sandbox, fixture-backed, or metadata-only memory-chain work.

Do not use this profile to broaden scope into a new subsystem landing unless the prompt explicitly authorizes that expansion. If the task is explicitly scoped as an even narrower surgical repair, follow [`codex_narrow_repair_task_template.md`](codex_narrow_repair_task_template.md) and cite why this recovery profile is not the controlling shape.

## First action

Inspect the tree first:

```bash
git status --short
```

Use that status as the recovery baseline before editing, testing, finalizing, committing, or creating PR metadata.

## Classify current changes

Classify every dirty path before repair:

- `task-owned`: files explicitly in the current task, profile, capability, or task slug scope;
- `generated-expected`: deterministic outputs expected from allowed docs, matrix, audit, finalizer, or fixture generation;
- `unrelated`: pre-existing or operator-owned changes outside the current task scope;
- `unknown`: changes whose source or ownership is unclear.

Unknown dirty files block commit. Unrelated files must not be hidden, reverted, or absorbed into the task without explicit ownership.

## Repair task-owned files in place

Repair task-owned files directly and minimally while preserving the whole-system contract for the original task. Do not mask failures by deleting required evidence, loosening tests, weakening docs, bypassing audits, or shrinking required matrix/proof/capability/doc obligations.

## Respect fixture-root ownership

For metadata-verification tasks, fixture roots must match the declared capability ID or task slug unless the prompt declares a different root. Update only task-owned fixture roots. Do not edit unrelated fixture roots to satisfy tests. If generated expected data changes, ensure it is deterministic and tied to the current capability/task slug.

## Re-run failing lanes and refresh evidence

After repair, re-run the failing validation lanes and any dependent evidence refresh required by the landing contract. If strict-audit repair, generated-artifact cleanup, fixture regeneration, or docs bootstrap makes matrix, landing-gate, supervisor, or finalizer evidence stale, refresh that evidence in the same recovery task when allowed.

## Do not bypass finalizer

Recovery does not bypass the two-phase finalizer. The finalizer remains the landing authority described in [`codex_finalize_landing.md`](codex_finalize_landing.md) and [`codex_validation_and_landing_contract.md`](codex_validation_and_landing_contract.md).

## Commit and PR metadata hard stops

Do not commit unless the pre-commit finalizer returns `ready_to_commit`. Do not create PR metadata or call `make_pr` unless the post-commit/pr-metadata finalizer returns `ready_for_pr_metadata` and the PR metadata guard returns `pr_metadata_guard_ready`.

`manual_review_required`, `unknown_dirty_tree`, failed required lanes, stale evidence without an allowed refresh, or blocked PR metadata guard are hard stops.

## Preserve runtime and authority boundaries

Preserve all no-runtime, no-authority, no-prompt-assembly, no-action-execution, no-external-disclosure, and no-real-memory-mutation boundaries. Recovery may repair metadata, docs, tests, fixtures, and deterministic review artifacts; it does not grant live memory writes, memory-chain advancement, provider calls, prompt export, policy truth, consent, external disclosure, or runtime authority.

## Recovery report addendum fields

Add these fields to the normal final report when using this recovery profile:

- recovery baseline from `git status --short`;
- dirty-path classification summary;
- task-owned files repaired;
- generated-expected artifacts refreshed or cleaned;
- unrelated or unknown changes found, with disposition;
- fixture-root ownership confirmation;
- failing lanes reproduced and rerun;
- stale evidence refresh result, if applicable;
- finalizer and PR metadata guard decisions;
- remaining risks or blockers.
