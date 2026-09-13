# Maintenance-loop operator activation

After watchdog idle proof, `render-scheduler-config` and `doctor-scheduler` seal and
inspect an exact digest-bound cadence profile; they never start it. The operator may
then run `render-daemon-adoption --enabled` to separately bind that exact profile for
`sentientosd`, or use `print-scheduler-command` for a manual bounded run.
Changing watchdog configuration requires a new profile. First-boot autonomy and
interval metadata is not scheduling authority. No OS scheduler entry is installed.

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
8. Run `doctor-scheduler`, then explicitly render daemon adoption with an external
   ownership-evidence path, shutdown bound, and re-entry delay. Set
   `SENTIENTOS_MAINTENANCE_SCHEDULER_ADOPTION_CONFIG` to that adoption file and start
   `sentientosd`. The daemon is not started by activation tooling.

No adoption is inferred from scheduler presence, candidate contents, watchdog state,
repository contents, or first-boot `architect_autonomy`, `codex_interval`, `codex_mode`,
or `codex_max_iterations`. Adoption owns lifecycle only: it creates no candidate or
lease and grants no implementation, validation, Git, publication, provider, network,
credential, host-actuation, or runtime-code-adoption authority. Locking uses `fcntl`, so
daemon scheduler adoption is POSIX-only.

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
