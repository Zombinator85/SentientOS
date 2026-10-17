# Sequence 315 — Expose verified recovery state to the transition operator

PR #2311 made the transition controller’s existing recovery diagnostics visible in the read-only live status: exact recovery reason, outstanding stage, replay-forbidden barrier, and digests of semantically verified journal entries. The new acceptance test confirms these values survive the status projection and that reading status does not advance a stage or append to the journal.

This narrows an important operator gap after sequences 313–314: an interrupted process remains fail-closed, while status now identifies what is outstanding and what history was semantically verified. It adds no automatic retry, reconciliation, token reconstruction, stage execution, or authority.

The change merged normally as `4d5c8347a1687f7faeedabdf3006df8140ba146a`, tree `b7eca92c69ba32f05fc3d3b2c4cc4ecbb9ddc459`. The exact acceptance node, complete pytest-with-coverage, strict Quality Gate, and full post-merge source CI passed. An optional post-merge invitation workflow failed with a 403 while posting a nonessential comment; it is not required and no write permission was added.

Sequence 286’s nine known and one unidentified unrecoverable payloads remain unresolved. The stale sequence-178 workspace remains untouched.
