# Windows live commissioning

The commissioning runner composes the existing live-bootstrap, Windows host-readiness,
deterministic maintenance canary, production wake, and Windows deployment APIs. It does
not create another maintenance loop and never registers, deletes, or otherwise mutates a
Task Scheduler task. All CLI output is canonical JSON.

## Real-machine flow (`C:\SentientOS`)

1. Copy and fill one live-bootstrap manifest for `C:\SentientOS`. Keep its external
   custody root outside the repository and bind its expected SHA and tracked base.
2. Run the read-only preflight:

   ```powershell
   python C:\SentientOS\scripts\maintenance_windows_live_commissioning.py doctor --manifest C:\SentientOS\operator\windows-live-bootstrap.json --state-root D:\SentientOS-Custody\commissioning
   ```

   Continue only when its status is `windows_commissioning_ready`; warnings never count
   as readiness.
3. Make the one explicitly authorized invocation:

   ```powershell
   python C:\SentientOS\scripts\maintenance_windows_live_commissioning.py commission-once --manifest C:\SentientOS\operator\windows-live-bootstrap.json --state-root D:\SentientOS-Custody\commissioning --create-custody-directories --authorize-canary-defect
   ```

4. Require `windows_commissioning_completed` and inspect the digest-chained receipt with
   `inspect --state-root D:\SentientOS-Custody\commissioning`.
5. Obtain the sealed preview with
   `print-scheduler-install-command --state-root D:\SentientOS-Custody\commissioning`.
   This prints the existing deployment argv and PowerShell representation but does not
   execute either.
6. The operator separately and explicitly decides whether to run that exact scheduler
   registration command.

The invocation discovers Python, Git, Codex, and PowerShell through the existing host
inspector and takes all component configuration paths from the rendered bundle. It does
not inspect credential bytes. Phase custody is persisted after each successful boundary,
so rerunning reconciles an introduced defect or already-published repair rather than
creating another probe, repair, publication, receipt, or command effect.

## STOP-first recovery

Place the existing `STOP` marker before recovery or rollback investigation. The runner
checks STOP before bootstrap effects, before canary mutation, immediately before wake,
and after wake. A present marker blocks further effects and is never deleted. Preserve
all existing custody and receipts; after investigating and applying the existing
operator-controlled STOP procedure, rerun the same commissioning command to reconcile
the recorded phase.
