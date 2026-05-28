# Codex PR Metadata Guard

`sentientos/codex_pr_metadata_guard.py` and `scripts/codex_pr_metadata_guard.py` provide a repo-local proof guard that must pass before PR metadata or `make_pr` is created.

The guard is a local validator only. It does not commit, does not create PR metadata, does not call GitHub/provider/network APIs, and does not widen runtime authority.

## Required normal-task command

```bash
python scripts/codex_pr_metadata_guard.py verify \
  --title "<COMMIT_TITLE>" \
  --intended-commit-title "<COMMIT_TITLE>" \
  --pre-commit-finalizer-json "/tmp/<task>_pre_commit.json" \
  --pr-metadata-finalizer-json "/tmp/<task>_pr_metadata.json" \
  --matrix-json-path /tmp/work_item_review_packet_matrix.json \
  --summary
```

The command must return `pr_metadata_guard_ready` before `make_pr`.

## Required validation-only command

```bash
python scripts/codex_pr_metadata_guard.py verify \
  --title "<COMMIT_TITLE>" \
  --intended-commit-title "<COMMIT_TITLE>" \
  --validation-only \
  --pr-metadata-finalizer-json "/tmp/<task>_pr_metadata.json" \
  --matrix-json-path /tmp/work_item_review_packet_matrix.json \
  --summary
```

Validation-only mode may omit the pre-commit finalizer only when no source/doc/test changes are present and no commit is being created.

## Proof checks

For normal source/doc/test tasks the guard requires:

- pre-commit finalizer artifact exists and has decision `ready_to_commit`.
- pr-metadata finalizer artifact exists and has decision `ready_for_pr_metadata`.
- CLI title and intended commit title match finalizer artifact titles when present.
- matrix artifact exists and has status `passed` with zero required failures.
- PR landing gate evidence in the pr-metadata finalizer is passed/equivalent.
- Codex Landing Supervisor evidence in the pr-metadata finalizer is ready/equivalent.
- dirty-tree evidence is clean/equivalent.
- stale evidence refresh is not blocking (`not_required` or `succeeded`).

A finalizer artifact alone is not enough if this guard reports a blocked status.

## Decision statuses

- `pr_metadata_guard_ready`
- `pr_metadata_guard_blocked_missing_pre_commit_finalizer`
- `pr_metadata_guard_blocked_missing_pr_metadata_finalizer`
- `pr_metadata_guard_blocked_pre_commit_not_ready`
- `pr_metadata_guard_blocked_pr_metadata_not_ready`
- `pr_metadata_guard_blocked_title_mismatch`
- `pr_metadata_guard_blocked_matrix_failed`
- `pr_metadata_guard_blocked_stale_evidence`
- `pr_metadata_guard_blocked_dirty_tree`
- `pr_metadata_guard_blocked_validation_only_mismatch`
- `pr_metadata_guard_failed`
