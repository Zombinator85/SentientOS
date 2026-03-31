# First Integrity Issue Onboarding

Fixing your first audit integrity issue is a practical onboarding milestone.
This guide explains the repair flow and how to record your first contribution.

For public↔internal terminology mappings, see
[PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md).

1. Pick an integrity issue listed in [OPEN_WOUNDS.md](OPEN_WOUNDS.md).
2. Use `python fix_audit_schema.py logs/FILE` to repair the issue.
3. Commit the repaired log with a short message describing the fix.
4. Open a pull request using the **Share Your Contributor Story** template.
5. Once merged, add your name under **Audit Contributors** in
   `CONTRIBUTORS.md`.

A short walkthrough can be found in `docs/video_procedure_guide.md` (or the
upcoming clip noted there).

Internal/cultural prose may still use governance control plane (internal
codename: cathedral) or operator procedure (internal codename: ritual), but
this onboarding guide keeps engineering terms primary for new contributors.

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.
