# Onboarding Walkthrough

This short screenplay demonstrates the typical procedure flow.

1. **Contributor** proposes a new tag in `tags.py` and opens a pull request.
2. **Reviewer** runs `python verify_audits.py logs/` and posts the summary.
3. A malformed entry is found. The reviewer runs `python cleanup_audit.py logs/` and commits the cleaned log.
4. **Steward** welcomes the contributor, blesses the PR, and records the event in the audit log.

Consider turning these steps into a quick GIF or video for new arrivals.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
