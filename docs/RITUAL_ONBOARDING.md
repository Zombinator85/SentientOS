# Operator Procedure Onboarding Checklist

This one-page checklist is the default onboarding path for first-time
contributors.

1. Read the [Tag Extension Guide](TAG_EXTENSION_GUIDE.md),
   [Contribution Contract](https://github.com/Zombinator85/SentientOS/blob/main/CONTRIBUTING.md), and
   [Contributor expectations](https://github.com/Zombinator85/SentientOS/blob/main/CONTRIBUTING.md).
2. Open a pull request and request reviewer assignment.
3. Complete reviewer sign-off in the PR description after feedback is handled.
4. Introduce yourself in the community channel.
5. For each new script, call `require_admin_banner()` and then
   `require_lumos_approval()` at module startup.
6. Note that automated policy workers may mark unattended operations for later
   human review.

## Why audit history matters

Audit logs preserve operational history, investigation context, and governance
traceability. Treat each entry as a durable operational record.

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.
