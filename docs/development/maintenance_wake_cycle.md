# Bounded maintenance wake cycle

`scripts/maintenance_wake_cycle.py` is an externally invoked, recovery-first coordinator. It installs no scheduler and grants no maintenance authority. Its outer nonblocking lock serializes wake invocations while the health probe and autonomy cycle retain their own locks and business decisions.

The closed configuration explicitly binds repository identity and root, exact base SHA, both component configuration paths, a private external wake-state root, receipt journal, shared outer `STOP` marker, and caller-supplied evaluation time. Doctor mode requires both component doctors and exact agreement over repository, base, governed-signal custody, activation/profile custody, inbox custody, and configured component STOP boundaries.

`wake-once` inspects autonomy first. Active, interrupted, waiting, publication-pending, inbox-candidate, or governed-source custody bypasses diagnosis and advances the existing autonomy cycle once. Only terminally idle custody permits one health probe. A healthy result terminates idle; findings cause a second STOP observation and at most one autonomy-cycle call. The digest-chained wake receipt binds observations, decisions, component results, terminal custody, and bounded effect counts without copying credentials, transcripts, validator bodies, or environment values.

The only commands are `doctor`, `wake-once`, `inspect`, `inspect-receipts`, and `print-run-command`. Output is canonical JSON. `print-run-command` returns argv with `shell: false` and `scheduler_installation: false`.
