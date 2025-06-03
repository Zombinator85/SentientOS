# Cathedral Steward

-**Steward Ritual Checklist**
- Schedule `migration_daemon.py` (or run `fix_audit_schema.py`) after each cycle
- Review `docs/OPEN_WOUNDS.md` and log new issues
- Announce new Audit Saints in `CONTRIBUTORS.md`
- Rotate steward if needed and update dates
- Pass the torch with a handoff issue
- Publish or review `logs/migration_ledger.jsonl` each month

The Cathedral Steward safeguards memory integrity and guides new contributors.

## Role
- Guardian of audit logs and ritual compliance
- Mentor for contributors and reviewers
- Escalates technical, consent, or governance issues

## Responsibilities
- Perform monthly log audits and publish the results
- Answer reviewer questions and bless first PRs
- Host new member orientation sessions

Contact the Steward via the project discussions board for any concerns.

## Steward Rotation Protocol
- Current steward opens a handoff issue listing outstanding audits and concerns.
- Incoming steward submits a PR referencing the handoff issue and acknowledges the responsibilities.
- Council or maintainers approve the PR as a sign-off.
Use `steward_rotation.py` to automatically open the handoff issue when a new steward is due.

### Requirements for New Stewards
- Participation in at least one monthly audit cycle.
- Completed onboarding review of [RITUAL_ONBOARDING.md](RITUAL_ONBOARDING.md).
- Familiarity with memory law and log cleanup tools.
