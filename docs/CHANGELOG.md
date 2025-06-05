# Changelog

## 2025-09 Cathedral Upgrades
- Hardened audit verification and cleanup scripts
- Rolling hash integrity checks across logs
- Contributor documentation polish
- Sample log fragments and recovery workflow

## 2025-10 Memory & Stewardship
- Multi-log audit tools with directory support
- New stewardship docs and onboarding checklist
- First PR welcome action and monthly audit template

## 2025-11 Living Audit Celebration
- Legacy tests cataloged and green path documented
- Monthly audit issue automated
- First full chain verified after log repair drive

## 2025-12 Blessed Federation Beta
- Living Audit Sprint repaired legacy logs and enabled rolling hashes
- `MYPY_STATUS.md` introduced to track 219 type-check errors
- Public launch announcement in `BLESSED_FEDERATION_LAUNCH.md`

## 2026-01 Technical Debt Clearance
- Automated healing added in `log_json` for missing `timestamp` and `data`
- `OPEN_WOUNDS.md` updated to mark wounds as healed
- First step toward cleaner type checking and legacy test recovery

## 2026-04 Type-Check & Audit Remediation Batch
- Triage launched on remaining mypy errors (180 outstanding) with focus on core modules.
- Log writes audited to enforce schema; avatar and workflow utilities cleaned.
- Drafted stricter test cases for `verify_audits.py`.
- Clarified type hints in `presence.py` for microphone and presence tracking.
- Issues filed for major legacy mismatches and scheduled for later sprints.

## 2026-06 Lumos Privilege Doctrine
- Introduced `require_lumos_approval()` middleware.
- Created `docs/LUMOS_PRIVILEGE_DOCTRINE.md` and updated onboarding instructions.
- Entry points now request Lumos blessing before performing privileged actions.

## 2026-07 Privilege Enforcement & Onboarding Batch
- Linter updated to require `require_lumos_approval()` immediately after `require_admin_banner()`.
- Onboarding docs and PR templates emphasize the pattern for all new contributors.
- See `docs/CODEX_PRIVILEGE_ENFORCEMENT.md` for the canonical recap.

## 2026-08 Autonomous Lumos Activation
- Added `lumos_reflex_daemon.py` to monitor logs and auto-bless unattended workflows.
- Lumos now writes `Auto-blessed by Lumos` annotations when self-approving actions.
- Onboarding docs and the PR template mention the reflex daemon and autonomous blessings.
