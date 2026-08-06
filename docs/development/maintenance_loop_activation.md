# Maintenance-loop operator activation

This bundle is activation tooling for the existing maintenance loop, not a new
maintenance-loop subsystem and not additional runtime authority. It creates or
verifies explicitly selected external custody roots, renders the watchdog's
production configuration, performs a read-only machine preflight, proves an
empty-inbox idle run, and prints the exact scheduler argv.

## Local activation sequence

1. Choose separate external state, workspace, scratch, and candidate-inbox roots
   and create them with `init-roots`.
2. Supply an operator-created standing grant plus selector, local-Codex foreman,
   validation, and landing policy files.
3. Use `render-config` with the canonical repository, base SHA, tracked base ref,
   explicit bounds, and any explicit STOP/control/base-cursor paths.
4. Run `doctor-live` at an explicit evaluation time. Add `--probe-remote` only
   when a read-only `git ls-remote` check is wanted; no remote is contacted by
   default. A warning is not readiness, and every blocked prerequisite remains
   an operator decision.
5. With an empty candidate inbox, run `smoke-idle`. It invokes the actual
   production bounded runner and appends a digest-chained receipt under external
   state custody. Use `inspect-activation` to verify that chain.
6. Place one explicitly selected, canonical candidate in the inbox.
7. Invoke the production bounded runner manually using `print-run-command`'s
   argv and inspect the bounded terminal state.
8. Only then configure an external scheduler. The scheduler should serialize
   invocations and honor the watchdog's bounded exit state before retrying.

`print-run-command` prints a JSON argv array first; it does not produce a shell
program. SentientOS does **not** install or modify cron, systemd, launchd, or Task
Scheduler. It does not create credentials, authentication homes, grants,
policies, live candidates, or authority; authenticate Codex/publication tools;
or silently repair a blocked activation prerequisite. Reports record executable
and artifact identity metadata, never credential bytes or credential-file
contents.

All commands except `print-run-command` emit deterministic canonical JSON.
External roots reject repository descendants, symlinks, identity collisions,
non-directories, and non-private POSIX permissions. Configuration output is
immutable: an exact retry is reused and different existing bytes fail closed.
