# Sequence 505 — reconcile hosted verification of stage approval time windows

This append-only continuation closes the pending-verification statement recorded at sequence 504. Sequence 504 itself is preserved byte-for-byte; this record documents the later hosted results and merge.

Candidate `b12f5164dd59b55c7095c7fc689328e2b54f8abd` (tree `43a084883d35195307ea4ab2aa051f91b291ddf3`) passed the PR-triggered checks. The Required Quality Gate passed on run `39521676814`, including exact-candidate acceptance, hosted Administrator strict audits, immutability verification, finalization, and the distinct pre-publication PR metadata guard. Its landing evidence artifact `12310943639` was independently downloaded and matched digest `sha256:9f5ef1518aecdeaab4fd3a6a0765bc6491ab7b78c49b6ca5d121eedc2cc83483`.

The candidate's source validation, self-check, docs, Helm, build, invariants, CPU smoke, and lint runs also passed. PR #2512 merged with history preserved as merge `8bb33dffb4be129e9a72a198b74f46d8d625c36a`, whose ordered parents are verified prior `main` `5d5f18d55214ac8fefc965e0a523015395a7d989` and candidate `b12f5164dd59b55c7095c7fc689328e2b54f8abd`. The merge tree equals the candidate tree. GitHub's branch endpoint and independent commit readback confirmed that `main` resolved to this merge.

All post-merge checks passed on the merge commit: Required Quality Gate, source validation, full self-check, Helm, docs, build, CPU smoke, invariants, and Pages deployment. Forge Smoke was skipped by its workflow condition. The exact source branch checks include the 62 focused transition and authenticated-operator tests in supplemental local runs; those local results are not represented as exact-candidate evidence. No production transition or inference ran.

The merge is integrated and its required verification is complete. No approval schema or authority boundary changed beyond sequence 504's timestamp validation. Sequence 504's historical pending status is superseded by this later append-only reconciliation, not rewritten.

The current verified main merge is `8bb33dffb4be129e9a72a198b74f46d8d625c36a` with tree `43a084883d35195307ea4ab2aa051f91b291ddf3`.
