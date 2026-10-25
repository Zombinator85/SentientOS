# Sequence 654: Record regression timeout recovery state

[untested] The existing local candidate remains commit `c58d9d2bb9790a7ec1aa5bf0770174b22389f52d`, tree `02e08b8355e2b1b2ff1a7d25ad2bb5bc125b77f4`, on `codex/construct-sentientos-s655-consolidate-landing-recovery`. A fresh read-only source preflight confirms the branch is clean and based on remote main `22de4777961f5301a8d9a62d432c4ce561a79939`; the status is `unpublished_candidate_requires_reconciliation` because the local candidate has not been published.

The docs dependencies were installed in `/tmp/sentientos-verification-venv` using the repository's documented editable docs extra and canonical minimal requirements. The docs dependency check passed and MkDocs generated 616 pages. Construction continuation custody verified 653 segments before this recovery record.

The canonical regression command did not complete. The verbose run collected 156 items and stopped at 79% on `tests/test_dashboard_drift_api.py::test_drift_recent_rejects_invalid_n`; an external five-minute cap ended it with exit 124. Running that exact node alone under a 90-second cap also ended with exit 124 and no recorded outcome. A prior quiet run was interrupted after prolonged no-progress output; its provenance reported zero accepted outcomes and unavailable metrics. Generated runtime residue was restored or removed; the candidate worktree is clean.

The candidate is not validated, so no PR was opened. Resume by diagnosing the isolated dashboard test hang, obtaining a complete canonical regression report, and then proceeding through the normal hosted Quality Gate, CI, merge, and post-merge evidence gates. Do not treat timeout, partial progress, docs success, or custody success as a passing regression suite.

Evidence: `work/construction/evidence/0654-regression-timeout-recovery.json` (SHA-256 `b208bee972b1a595e3cc8854952b23874b3bf5e8f3b94869697dd17ce37af7f1`).
