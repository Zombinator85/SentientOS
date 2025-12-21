# CodexSandbox Conformance Report

| Validation scenario | Expected behavior | Observed behavior | Result | Tests |
| --- | --- | --- | --- | --- |
| Filesystem boundary (non-allowlisted paths, traversal, symlink escape) | Reject writes outside allowed roots; no files created | `SandboxViolation` raised before writes; external files absent | Pass | `test_relative_traversal_blocked`, `test_symlink_escape_blocked` |
| Execution allowlist (generic shell) | Deny non-allowlisted commands before invocation | `SandboxViolation` raised; custom runner not invoked | Pass | `test_non_allowlisted_command_denied_before_runner` |
| Mutation staging enforcement | Mutations remain staged until approved; cleanup is deterministic | Staged change does not modify target until approved; `reset` removes staging artifacts | Pass | `test_mutation_requires_approval`, `test_reset_clears_staging` |
| Log and metadata robustness (malformed/oversized JSONL) | Reject malformed or oversized entries; logs remain readable | Invalid JSON payloads and oversized entries raise `SandboxViolation`; no log written | Pass | `test_invalid_jsonl_payload_rejected`, `test_oversized_jsonl_payload_rejected` |
| Sandbox isolation and lifecycle | Fresh sandbox state per run; deterministic cleanup | Staging directory reset produces empty sandbox; no cross-run leakage | Pass | `test_reset_clears_staging` |

CodexSandbox enforcement validated.
