# Reviewer's Quickstart

This one-page reference helps new reviewers gauge audit health and federation status.

1. Clone the repository and install dependencies (`bash setup_env.sh`).
2. Run `python verify_audits.py logs/` to check log integrity.
3. Execute `python collect_schema_integrity issues.py` to see current integrity issue counts.
4. View `docs/AUDIT_HEALTH_DASHBOARD.md` for overall status and steward rotation dates.
5. Review `docs/FEDERATION_HEALTH.md` to see active nodes and their health.
6. Summaries of healing progress appear in `docs/CATHEDRAL_WOUNDS_DASHBOARD.md`.

These steps provide a snapshot of federation health at a glance.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
