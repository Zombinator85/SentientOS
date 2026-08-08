# Windows live-host readiness and maintenance canary

`scripts/maintenance_windows_host_readiness.py` provides a JSON-only, fail-closed
operator workflow.  It never installs, changes, queries, or deletes a Task Scheduler
task.  Executable presence is not evidence of Codex authentication, and reports never
inspect credential files, environment dumps, tokens, or auth material.

The closed host manifest explicitly binds the repository and expected SHA; Python,
Git, and Codex executables; wake and activation/profile configuration; collector,
autonomy, and wake custody; the existing deployment manifest and output; remote/base
ref and task name; and the canary source, exact pytest node, and allowed path boundary.
Missing authority or custody values are errors. `inspect-host` may report discovered
paths as facts, but the operator must explicitly accept them when rendering a manifest.

## Live bring-up

1. Pull the exact expected `main` commit.
2. From the intended repository root (for example, `C:\SentientOS`), run
   `inspect-host --repository-root C:\SentientOS` and review its read-only JSON
   facts. `inspect-host` discovers Python, Git, Codex, and PowerShell paths and
   reports them for explicit host-manifest acceptance; the operator does not need
   to discover those executable paths manually before running it.
3. Explicitly render and approve the closed host manifest with
   `render-host-manifest`; then run `verify-host-manifest`.
4. Run `doctor-live`. Warnings never produce `windows_host_ready`.
5. Render and verify the existing Windows deployment bundle. Do not register it.
6. Run `print-manual-canary-command`, review the argv-only plan, deliberately create
   the fixture defect, and invoke the existing production wake once with a fresh UTC
   evaluation time.
7. Run `inspect-canary` until it reports `canary_completed`. Inspection never repairs.
8. Only after completion, print and separately register the existing Task Scheduler
   bundle using the deployment workflow.

The dedicated fixture is
`tests/fixtures/maintenance_windows_live_canary.txt`; its exact validation node is
`tests/test_maintenance_windows_host_readiness.py::test_windows_live_canary_content_is_canonical`.
It exists only for an operator-triggered live-host validation. Its canonical repair is
the single boring line `sentientos-windows-live-host-canary: healthy`. The allowed
maintenance boundary must designate only that fixture (or its dedicated fixture
directory), never configuration, credentials, grants, scheduler state, implementation
code, or user data.

The manual sequence is readiness, explicit defect, one production wake, receipt
inspection, deterministic repair validation, exactly one commit, fast-forward
publication, closure/idle verification, and confirmation that the remote base ref is
the repair commit. The command printer only returns argv/data and performs none of
these steps.

Rollback remains: **STOP first**, disable/delete the scheduled task if one exists,
inspect canonical custody, and preserve receipts and state.
