## 2026-10-13 checkpoint — prevent legacy oracle hashes re-entering cognition

- Continued from source commit 710846a7708f0f1a6289187051c26286228f6115 / tree 1e67c21c01470218fac24245c1aff670022732aa and verified continuation HEAD 6770021fb698b9dfc2e128d330435c826578a586 / tree 96e299ca380507484b0e8f0054b0905b1f80a861.
- The remaining oracle-privacy review found legacy unkeyed task/plan digests could still be projected from historical intervention and model-replacement runs into World-State or admitted history. Historical receipts and plans remain readable and verifiable, but those unkeyed low-entropy identities no longer enter new cognition-facing projections.
- Both experiment owners now omit legacy objective outcomes from new World-State projection. New A/B objective runs are admitted only from a verified salted task plan; v1 plans cannot start a new inference campaign. The objective summary adapter explicitly withholds legacy oracle commitments.
- The resident cognition owner filters legacy objective facts from writeback selection, current context, and bounded prior-history retrieval. Safe commitment posture is carried from the verified plan/descriptor through World-State and the existing bounded developmental-history projection. The family writeback adapter rejects legacy objective lineage rather than treating it as admissible.
- Production behavior and historical custody semantics were not changed. This is a narrow privacy/eligibility boundary; a missing safe posture fails closed for cognition while the original owner may still verify the artifact.

Validation on the exact published source bytes:
- Python compilation passed for the four changed owners and two changed test modules.
- Trailing-whitespace scan passed on all six changed Python files.
- Focused objective-scoring/history-intervention group, including the legacy exclusion regression: 34 passed.
- Task-family acquisition, adverse-example, progression, history feedback, and restart/no-replay controls: 5 passed.
- Isolated legacy-current-context regression: 1 passed.
- The governor root for subprocess tests was redirected to a temporary isolated path. No provider, production model, or external effect was used; endpoint outcomes are deterministic fixtures.

Source commit: 629805a99fdbdef5340eb2f96a3959720b0fd077
Source tree: 3dfabb4bbe6b7682c92f9ecc5c10d5a50ab3d188
Changed blob identities are recorded in the accompanying evidence JSON. Construction remains unverified for production.

Next: extend the source-backed multi-episode transfer control so a second distinct held-out task consumes the same admitted family history after restart, with recent irrelevant and adverse examples retained as controls; keep correctness, output change, and actual model learning claims separate.
