# Onboarding Walkthrough

This walkthrough demonstrates a standard contribution and audit-repair flow in
engineering terms first.

For public↔internal terminology mapping, see
[PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md).

1. **Contributor** proposes a tag change in `tags.py` and opens a pull request.
2. **Reviewer** runs `python verify_audits.py logs/` and posts the summary.
3. If a malformed audit entry is found, the reviewer runs
   `python cleanup_audit.py logs/` and commits the repair.
4. **Maintainer / governance authority (legacy term: council)** approves
   the pull request and records the decision in the audit log.

Internal project dialogue may refer to privileged approval (internal codename:
blessing) or operator procedure (legacy term: ritual). Public onboarding
guidance should keep those terms secondary.

Consider turning these steps into a short GIF or video for new contributors.

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.
