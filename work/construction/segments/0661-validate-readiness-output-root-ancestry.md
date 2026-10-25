# Sequence 661: Validate readiness output root ancestry

Changed the host fulfillment readiness runtime to compare resolved path components when rejecting repository-local output roots. A sibling external path whose name shares the repository prefix is accepted. Regression coverage confirms the accepted path remains metadata-only: the executor backend is not invoked and no host action is run. Existing repository-local rejection remains covered.

The task bootstrap was ready for `runtime_safety`. Exact task acceptance passed for both required nodes. Canonical regression passed: 168 passed, 16 skipped, zero failed (184 collected). Targeted mypy, docs dependency check, the 616-page documentation build, diff check, and construction custody through sequence 660 passed.

Candidate is locally validated on base `e3e2c12919b36248c6a018fcf193c35658a5b9e0` / tree `8860d5b6016a50b51a6c7cc3248bb476074c4fdd`; publication is pending normal governance.

Evidence: `work/construction/evidence/0661-validate-readiness-output-root-ancestry.json` (SHA-256 `3c885ae72cbf51a1f45c6960f02049f9b6775141ccee8e51076916e781bad796`).
