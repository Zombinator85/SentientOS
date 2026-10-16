## 2026-10-13 checkpoint — qualify execution evidence separately from independent observation

- Continued from remotely verified source commit `d1c4021d8c1e8287fcfbd704373dfd04bafd3cb0` / tree `1d51fb321564dad54f28434ba5609c9a7cfc0f27`.
- The objective measurement summary already derives `actual_nonsynthetic_inference_verified` from a canonical persisted invocation receipt, exact serving/request/model linkage, completed status, non-fallback execution, owner-reported local inference effect, and bound generation parameters. This is authenticated owner execution evidence; the source has no independent external backend attestation.
- Added an explicit per-condition `execution_evidence_posture`, plus measurement and progression fields `execution_evidence_scope` and `independent_backend_observation=false`. Existing boolean and historical fields remain unchanged. The progression carries each condition's posture forward, distinguishing fixture simulation/no-entry from an owner receipt that reports backend entry.
- The fresh-process test exercises three fixture episodes with simulation receipts, verifies that the non-synthetic inference flag remains false, and asserts the independent-observation field remains false. Existing positive owner-receipt path and interrupted recovery controls also pass.

Checks on published source:
- Three-episode fresh-process family transfer: passed.
- Bounded progression and interrupted scored-run recovery: 2 passed.
- Python compilation and UTF-8/NUL/whitespace checks passed.

Source commit: a5b6b0fd64b4ad7723b9b2faec70b2a9ff08d2fd
Source tree: 986ff07c34fb41ec9c8890084e48b5a9a845eb31
Changed blobs:
- `sentientos/resident_developmental_cognition.py`: `3c2a4b08c9d8d39c9c0610d4b2d277caef7e01ea`
- `tests/test_resident_developmental_cognition.py`: `f90ff6c76c12bc48fa0b66956606402e0688811b`
Construction remains unverified for production.

Next: inspect available exact local-model configuration and artifact custody without loading or invoking a model. If no authorized local backend/artifact exists, continue with source-level mechanisms that improve reproducible acquisition evaluation while retaining fixture-vs-runtime evidence separation.
