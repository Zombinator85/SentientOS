# Sequence 587 — fail closed on a missing epistemic update event

PR #2630 adds an exact source-validation regression for a state transaction whose state and transaction records were published but whose matching update event was removed. Restart fails closed in the owner's state/event pairing verification, before cognitive projection or mutation-receipt recovery can expose that incomplete generation. The test confirms the admission ledger and the already-published state receipt remain byte-identical and the event remains absent.

The first exact candidate, `d13b7613bfd55ce149e489a7e0abffbfa763d9e3`, failed CI source validation (run 39833859278; one failure among 412 selected tests) because the test incorrectly expected owner reconstruction to succeed before a later projection rejection. Hosted logs showed the implementation correctly rejected the missing event immediately with `epistemic_update_state_pairing_ambiguous`. The test was corrected to assert this earlier fail-closed boundary; no production code or verification gate was changed.

Corrected candidate `ccf77144239045afeebbc3eb8ee2b2569ca67c69` passed all eight hosted workflows. CI run 39834537834 reported 143 passed, 13 skipped, zero failed; its source-validation lifecycle and all 14 acceptance nodes passed, including the exact missing-event regression. The strict Quality Gate passed (run 39834564587), including Administrator audits, audit immutability, hosted finalization, and the separate PR metadata guard. Lint Benchmark, Codex CI, Gradient, Release, Invariants, and Docker also passed. The full test run's provenance and source-validation artifacts were inspected; source-validation checkout `8a9573d55f60bcdf344b3c2eba326c6182e95d5b` has an identical tree to the candidate.

PR #2630 merged with a normal merge commit as `ffeac63ad9e6bfbec29ada77441a5e8b1409d5aa`. GitHub compared the candidate and merge commit with no file differences. The merged tree is `f70894adb9c96463c5feb2099be2e4f97552be16`. PR #2629's sequence 586 evidence is included as an ancestor and was merged through this verified descendant. The failed first attempt remains visible in append-only history and is recorded above.

No inference or production transition occurred.

Sequence: 587 (verified source integration)