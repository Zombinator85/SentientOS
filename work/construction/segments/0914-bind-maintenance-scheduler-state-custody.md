# Sequence 914: bind maintenance scheduler state custody to stable directory descriptors

The maintenance scheduler previously validated the configured state path before later path-based lock, journal, and stop-marker operations. POSIX execution now opens the symlink-free state ancestry with `O_NOFOLLOW` and performs leaf operations relative to the retained directory descriptor; leaf files must be regular and are opened without following links. Race regressions cover ancestry replacement, redirection after descriptor acquisition, and symlinks at each state leaf. This is an `[untested]` construction increment pending exact-candidate hosted gates.

Candidate implementation commit: `b85c39bb8a20e1b579175ad664b637b95ba8b837`, tree `29dac813d4d734cd8fdfcc6e54a2061c2723eb83`, based on verified main `a4908951510ba4b8758a439e248f1026270324d1`, tree `0c61e962bdb7482b6976669fb29c5951a97da0d2`.

Focused tests: 52 passed, zero failed or skipped. Exact task acceptance passed on the verified base before commit. Targeted mypy passed; `make docs` generated 617 pages; `git diff --check` passed.

The first test invocation exposed missing `jinja2` in the managed runtime. The documented minimal harness and docs extras were installed in a workspace-local virtual environment, using the configured network path. One initial package installation attempt failed because `/tmp` had no free space; redirecting `TMPDIR` to workspace storage allowed the documented installation to complete. No managed-environment settings or Administrator requirements were changed. Hosted acceptance remains pending.

Evidence record: `work/construction/evidence/0914-bind-maintenance-scheduler-state-custody.json`.
