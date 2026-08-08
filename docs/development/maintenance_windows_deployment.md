# Windows maintenance wake deployment

This operator-facing bundle renders a PowerShell launcher, a Windows Task Scheduler XML definition, and a digest index for the existing production `maintenance_wake_cycle.py` CLI. It is inert deployment evidence: the repository never registers, enables, disables, or deletes a scheduled task, never handles credentials, and never expands runtime authority.

## Manifest and commands

Start with `python scripts/maintenance_windows_deployment.py write-template --output <manifest.json>`, then replace every sample with explicit host values. The closed manifest requires the repository root and exact expected SHA; absolute Windows paths for Python, wake configuration, external logs, deployment output, working directory, and stdout/stderr; task name; trigger type and interval or exact schedule; timeout; execution account mode; battery, wake, and missed-run choices; and a maximum concurrent instance count of exactly one. External custody paths must not be beneath the repository. Relative paths, unsupported scheduler policy, credential or secret-like fields, and inferred values fail closed.

Use `render --manifest <manifest.json> --output-directory <local-custody-path>` to produce `maintenance-wake.ps1`, `maintenance-wake-task.xml`, and `maintenance-wake-deployment-index.json`. Rendering is deterministic and immutable: an exact retry succeeds without rewriting bytes, while a conflicting existing artifact blocks. `verify` recomputes the manifest and artifact digests, parses the XML, checks serialized execution and launcher-only task action, and confirms the launcher uses an argument array for the existing wake CLI. `inspect`, `print-preflight-command`, `print-install-command`, and `print-uninstall-command` emit canonical JSON only. The latter commands are previews; they do not execute `git`, PowerShell, `schtasks`, or scheduler APIs.

The launcher captures a fresh UTC evaluation timestamp when invoked, sets the exact repository working directory, and uses `Start-Process -FilePath` with an argument array to run `scripts/maintenance_wake_cycle.py --config <explicit-path> wake-once`. It redirects output to the explicit external files and returns the child exit code. It performs no Git, scheduler, credential, publication, or repository mutation itself. The XML runs only that launcher, uses `IgnoreNew` to prevent overlap, applies the explicit timeout and host policy, and contains no secrets.

## Live deployment order

1. Pull the exact `main` revision recorded in the manifest and verify `HEAD` equals it.
2. Prepare the real externally custodied activation profile and wake configuration.
3. Run all existing activation/profile and wake doctors at a fresh UTC evaluation time.
4. Run the existing idle smoke check.
5. Run one manual `wake-once` canary.
6. Inspect wake receipts and remote publication state; readiness evidence is not publication authority.
7. Render the Windows deployment bundle.
8. Inspect the generated PowerShell, XML, and digest index, then run `verify`.
9. The operator explicitly runs the printed native XML registration command. The repository does not run it.
10. Verify one scheduled invocation and inspect its external stdout, stderr, receipts, custody, and publication state.
11. Only then leave scheduling enabled under local operator authority.

Paths containing spaces remain separate argv entries in command previews and single-quoted literal values in PowerShell. Review the task execution account mode carefully: selecting an account mode is an explicit operator privilege decision, not a renderer default or grant.

## Rollback

1. Place the governed `STOP` marker **first** so a waking process fails safe at its existing boundary.
2. Disable or delete the scheduled task using operator-controlled Windows tooling (the uninstall preview prints a deletion command but never runs it).
3. Inspect active maintenance custody, wake receipts, process state, and any remote publication state before further action.
4. Do **not** delete state or receipts to “reset” the system. They are the audit and recovery record.

Rollback does not revoke or rewrite history, and generated bundle verification is not evidence that installation occurred.
