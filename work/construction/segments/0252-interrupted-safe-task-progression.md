# Sequence 252 - Interrupted safe checks resume before dependent work

The plan executor now resumes an interrupted `diagnostic` or `verify` task after checking that the task is non-destructive and the task identity is still bound to the exact plan. The append-only journal records each replay as a numbered `retry_started` event. Repeated process interruption can therefore resume these allowlisted checks without losing attempt history; dependents proceed only after a terminal success is durably recorded.

Interrupted forge proposal and apply work remains unknown and is not replayed. The existing adversarial path continues independent tasks while skipping dependents of unknown or failed work. Journal recovery validates retry event sequence, task kind, non-destructive posture, attempt number, and digest chain.

Validation: goal executor run, plan, and work plan recovery suites passed (35 tests). Changed Python sources and tests compiled; `git diff --check` passed.

Limits: replay is limited to non-destructive allowlisted diagnostics and verification. This increment does not authorize mutation, guarantee goal completion, or resolve unknown outcomes for non-idempotent tasks. Later outcome-informed planning and broader partial goal progression remain open.
