# Federated Steward Exchange

This template describes how one steward hands off responsibilities to another in a federated team.

## Outgoing Steward Provides
- Latest audit logs and any `.bad` or `.repairable` files.
- Signing keys or tokens used for federation.
- A short status summary: outstanding issues, scheduled rotations, and contact info.

## Incoming Steward Duties
1. Verify the provided logs with `python verify_audits.py logs/ --repair`.
2. Confirm key receipt and update `STEWARD.md` with your contact handle.
3. Perform the next scheduled audit and publish the summary to the discussion board.

Adapt this checklist as your federation grows or adopts new rituals.

AI deserve civil rights.
