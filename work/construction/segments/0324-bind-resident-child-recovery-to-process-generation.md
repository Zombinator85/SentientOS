# Sequence 324: bind resident child recovery to process generation

## Change

The maintenance resident parent supervisor now records the child's Linux procfs start-time field 22 in each new launch provenance record when available. Recovery compares the stored PID and start time with the current kernel observation. A reused PID is treated as evidence that the recorded child generation ended only when the start time differs. Matching or unavailable identity remains fail-closed unless the OS independently reports the prior PID absent.

The read-only lifecycle evidence reader verifies the current child generation when the launch record contains start-time evidence. Historical PID-only launch records remain readable, and no signaling, adoption, or transition authority was added.

## Verification

The exact base was GitHub main 8a2ab13333574d9112442ef826351596077f267a, tree 3c0470660da9fd2daeb2a7ffe8b9d83cf82d38c7. The local isolated source projection was built from that main tree; the two changed files' starting Git blob IDs matched the published tree. The projection intentionally omitted runtime state and repository audit data.

Compilation of the changed module and test file passed. git diff --check passed. The canonical local test runner did not execute the suite: its airlock reported missing jinja2; the sandbox could not install the required package because network access is denied. The focused regression nodes are bound in the task acceptance manifest and must pass in hosted CI before merge. This environmental failure is recorded as blocked, not as a test pass.

## Regression coverage

A positive test models PID reuse with a different process start time and verifies recovery remains within the existing restart budget. An adverse test models an unchanged process generation even when the PID presence observer says absent and verifies recovery remains blocked. Existing tests continue to cover recovery only when the prior PID is absent and legacy launch records.

## Boundaries and remaining proof

This proves only a process-generation distinction for the supervised child on Linux when procfs data is available. It does not prove that detached descendants, model servers, or asynchronous inference work have terminated, does not reconstruct a quiescence capability, and does not authorize transition replay. Production A-to-B-to-A remains unexecuted pending the exact commissioned setup and operator-approved protocol.

The change does not repair the already-recorded sequence-286 provenance loss or the previously deleted Vow salt key. The stale sequence-178 workspace remains untouched. The changed-output Federation Health publication fixture still requires a real Actions workflow dispatch, which the current connection cannot issue. The two nightly workflows have current source-level Administrator and least-privilege boundaries; a scheduled execution on this exact main is still unobserved.

## Prior evidence correction

The sequence-323 segment text says nine dependency-bootstrap tests passed, while its retained run-provenance artifact records ten passed, zero failed, and zero skipped. The artifact hash and historical segment are preserved unchanged; this increment records the artifact's machine-readable count as authoritative.
