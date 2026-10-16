# Sequence 191 — Freeze independent strategy decision-quality criteria

Starting evidence HEAD: `a635cb69ef86784dfffb41593614b15b584ffe16`, tree `4ede07115b50465bddffed5c256112d53a8ab445`.

Added a versioned decision-quality rubric that is frozen against the exact situation and selected event identities before responses are scored. The criteria report separate outcomes for event citation identity, uncertainty under unverified applicability, observation requests under incomplete current evidence, renderer/observer separation, unsupported body modification, and causal claims that exceed source authority. Scores are a criterion vector with no arbitrary aggregate and no condition-label input.

Connected the rubric to multi-event packet construction and response scoring. It remains available for each valid condition proposal even if another condition is missing; aggregate causal comparison still requires all three scoreable responses. The integration test demonstrates an adverse history-present response failing several criteria while a history-withheld response passes the current-situation observation checks. The evaluator can preserve “indeterminate” where a proposal makes no applicability claim.

Validation: 35 embodied/transfer tests passed, including rubric tamper rejection; changed source/test compile and diff checks passed.

Source commit: `4c0ad56e428ceb4f4561acaec076ac218fff04b9`; tree `df676d1ca1a1030bc58a9ad17ec98aeeb2d13c04`. Source and test blobs were independently found in the live tree.

Limits: rules are fixture-tested evaluation criteria, not a validated universal utility function. The evaluator does not establish physical causation, admitted record custody, or model improvement. It deliberately returns no aggregate score or superiority claim.

Next: exercise contradictory, corrective, unrelated-newer, and environmental-change cases from actual admitted multi-event records, then connect the seven-episode progression and a fresh-process scoring recovery.