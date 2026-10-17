# Sequence 332: exercise the live Linux process-generation observer

## Verified transition-recovery acceptance

Required Quality Gate run `39076422714` validated integration commit `64d109a392dfe6c0d5e28a19b868fa6876634700`, whose tree `9f312d9c5554698ad8307fa8bea3fa163df5678a` exactly matches candidate `bcc518c8d45254c47b80e88f1a49396d904fcf09`. The integration commit has parents current main `8a2ab13333574d9112442ef826351596077f267a` and the candidate head. The hosted run completed all 26 selected tests with zero failures; both PID-reuse recovery and still-live-generation rejection passed. Exact acceptance binding and the hosted Administrator finalizer also passed. The finalizer returned `ready_for_pr_metadata` after the PR title was aligned before the run.

## Remaining verification gap

The recovery tests inject start-time observers, so they prove decision logic but do not call `_linux_process_start_ticks` against a real `/proc/<pid>/stat` record. The newline correction also repairs this procfs parser. Sequence 332 adds a Linux-only regression that reads the current process's field-22 start time twice and proves it is a stable nonnegative integer. The exact Quality Gate selection and its shell-continuation contract grow from 26 to 27 nodes.

## Verification boundary

Compilation and diff checks pass locally. The local projection cannot import the supervisor because a repository runtime dependency (`nacl`) is missing and its pytest bootstrap rejects this noncanonical projection. The real-procfs test, 27-node hosted acceptance, strict finalizer, and remaining required CI checks must pass on the new exact candidate before integration. No production process is started or mutated.
