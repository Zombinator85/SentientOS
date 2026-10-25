# Sequence 653: Consolidate the landing lifecycle reference

[untested] The recovery rail repeated the full landing sequence and status definitions already stated in the canonical Validation and Landing Contract. The recovery rail now links to that contract and states that its scope is recovery from missing or stale evidence. The canonical lifecycle requirements remain in the contract; no landing control, repository mutation authority, or runtime authority changed.

The change is documentation-only in `docs/development/codex_landing_evidence_recovery_rail.md`. The docs build was blocked before execution because `mkdocs` and `watchdog.observers` are missing in this environment. No dependencies were installed. `git diff --check` passed.

This is an uncommitted local construction increment based on verified main `22de4777961f5301a8d9a62d432c4ce561a79939`, tree `3312b3007d4133ec4f6ffc59de3445c58e68d056`. No commit, branch publication, or PR is claimed.

Evidence: `work/construction/evidence/0653-consolidate-landing-lifecycle-reference.json` (SHA-256 `185248ff51ba5d6b6308974b0b53bb1ce024d4ea514c039d948a686e50693b05`).
