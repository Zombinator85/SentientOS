# Sequence 212 — Work-plan execution boundary

## Source finding

The persisted work-plan CLI loads task command strings from JSON and passes diagnostic/verification commands to a shell. The same plan format can label a forge_apply task as non-destructive, while execution previously trusted that serialized flag for the mutation gate.

## Change

Diagnostic and verification work is restricted to exact built-in command identities and launched as argv using the running Python interpreter with shell execution disabled. Fetch and documentation task kinds reject command payloads. A forge_apply task is destructive by kind regardless of its serialized flag, and that effective classification is recorded in the task run.

## Validation

Seven focused executor plan/run tests passed, including rejection of a shell metacharacter payload without launch, direct argv execution of an allowlisted command, and recovery-mode denial of a forge_apply task falsely marked non-destructive. Both changed Python files compiled and the diff passed whitespace checks.

Adjacent goal-state tests were attempted and failed before exercising this change because their calls omit required keyword-only arguments. No code in that API or tests was changed.

## Continuation

Sequence 213 should inspect current runtime/resource observation and software succession outcome composition, then implement the highest-value causal gap supported by source. The genuine-model Codex pilot remains an operator workstream and is not a construction prerequisite.
