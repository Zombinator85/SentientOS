## 2026-10-12 — bind Forge run projections to remediation custody

- Source basis: verified remote `f47bed0a607b5e894dd6291ccf08cfdb603a0223`, tree `452455763c16a583dcce9cfb9f8f1722080af539`.
- `sentientos/forge_index.py` no longer treats artifact-catalog summaries or raw run-file discovery as a remediation completion signal. It asks `latest_run_for_pack()` to reconcile the immutable intent and final report.
- Auto-remediation attempt rows now project `succeeded` only when their exact pack/run pair matches the latest owner-reconciled completed report. Unmatched claims remain `unverified`; quarantine linkage uses the same owner.
- Preserved the genuine owner-produced completion positive control. A forged catalog-only claim and interrupted intent are negative controls.
- Focused Forge/remediation suites: 39 passed. Changed Python compilation and `git diff --check` passed. See `work/forge_remediation_projection_acceptance.json`.
- Production behavior and external consequences remain unverified; no remediation action or activation was run.
