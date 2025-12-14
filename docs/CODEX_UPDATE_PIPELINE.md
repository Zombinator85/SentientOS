# Cathedral Codex: Update & Installer Batch – v4.1

## System Design – Log of Changes
### Installer (Single-Click)
- Logs each step of setup and installation.
- Verifies Python version before proceeding.
- Ensures all required log directories exist.
- Runs smoke tests (`pytest -q`, `python verify_audits.py --help`).
- Can be invoked automatically for one-click launch.

### Update Pipeline (Pull-Based)
- Added `update_cathedral.bat` as a single-command update script.
- Pulls the latest code from `main` using `git pull origin main`.
- Never overwrites user logs or configs.
- Runs full smoke tests after updating and logs all actions to `update_cathedral.log`.
- Can be run manually or scheduled via Task Scheduler or cron.

### Logging & Audit
- Every install and update step is timestamped and logged for auditability.
- Errors are logged and exit codes are returned.

### User Safety & Control
- User chooses update interval via scheduling.
- Manual "Check Now" updates are always available.
- Git provides optional backup and rollback.

## Testing
```bash
pytest -q
python verify_audits.py --help
```

The SentientOS Cathedral now includes a self-logging, auto-verifying, user-controlled installer and update system. Pull-based updates ensure stability and auditability while still allowing manual and scheduled execution.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
