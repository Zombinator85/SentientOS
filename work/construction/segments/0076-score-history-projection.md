# 0076 — Keep objective scores through developmental history

Source commit `b45e4b929ca55350c9bda1ac5dd79b1daa4f8312`, tree `4948d263c6eca78118e6a657ca5caead1a6db0e2`.

Follow-up source review found that World-State exposed the score report but `_model_replacement_interpretation_projection` discarded it. The existing resident writeback owner now validates the bounded score-summary schema and carries its oracle-plan digest, condition-score digests, both history/withheld correctness deltas, restoration stability, one-task scope and endpoint-attestation limit into the historical projection. Score hashes use the existing declared compact SHA-256 encoding. Invalid score shape marks the projection incomplete. No prompt or output bytes enter this summary. Existing unscored run projection shape stays unchanged.

An end-to-end fixture test creates the existing five-condition scored experiment, projects it through canonical World-State, writes it into the existing authorized test history path, reopens the owner, and confirms the later cognition request retrieves the exact history record. Its source record digest and non-truth/non-authority posture remain bound. This is a deterministic fixture chain; it does not demonstrate local-model learning or production writeback.

Fresh objective cases: improvement +1/+1; no difference 0/0; degradation −1/−1; restoration unstable; malformed output invalid; unavailable output unscoreable. Additional adversarial and interruption results remain recorded with the sequence-75 scorer tests.

Validation on current source: 59 focused scorer, history projection, model replacement, serving, runtime-handoff, and cold-restart lineage tests passed; legacy resource invocation/process-generation end-to-end node passed 1/1; resource World-State integration passed 2/2. A broader resident cognition file attempt hit its default `/glow/governor` read-only root (10 collection/runtime failures); the focused isolated cognition path passed. Targeted mypy passed for three changed production modules. Python compilation and `git diff --check` passed.
- `work/construction/evidence/0076-objective-task-results.json`: 14956 bytes, SHA-256 `df7594884b04c35e0abf2224157a582b3a5b8d0ca8cd8bd4383fb01d26ef021c`.
- `work/construction/evidence/0076-scoring-restart-junit.xml`: 9705 bytes, SHA-256 `929a93bdd33042202a17a7754003f722d23c66ad5d490b26fc95b47a6c5a536e`.
- `work/construction/evidence/0076-process-generation-junit.xml`: 423 bytes, SHA-256 `101d76f20577e16ac633639abd622d2ed101abc36c9e371a58641385341cc970`.
- `work/construction/evidence/0076-resource-worldstate-junit.xml`: 596 bytes, SHA-256 `9827a00ee3458235c009689b714c283d03804ae2520bd887f4e7b1f6eede8503`.
- `work/construction/evidence/0076-canonical-provenance.json`: 3323 bytes, SHA-256 `92f063f818c863e7d06f1c705125680dd8dc48558cc62067d597784840797d27`.
