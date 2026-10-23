# Sequence 596 — freshness and withdrawn conclusions shape recovered planning

PR #2649 extends the recovered canonical-planning regression across stale, current, adverse, and withdrawn conclusion states. A supported state backed only by a stale binding remains review-required after restart and produces no work plan. A later admitted current binding for the exact proposition and model restores the verified-positive posture and preserves the existing plan-evidence identity assertions. The regression continues to reject cross-model inheritance and adverse evidence.

The final admitted `evidence_withdrawal` update withdraws the supported conclusion by returning its stance to unknown while retaining the immutable binding as provenance. After restart, planning returns to review-required and no goal run is created. The test does not claim that the evidence binding record itself was withdrawn: the resident mutation controller currently has no governed removal interface even though the lower-level state owner supports removed-binding deltas. That authority-bound removal path is the next dependency.

The test keeps canonical planning non-executing, asserts exact proposition/model scope, and checks that no serving session or model invocation occurs. No production code, inference, or authority changed.

The exact source candidate is `f825749e42def5bdc831becbfc3e97c6cc5a6aea`, tree `c334e2c0a225843910f1c8cb406b607d667fce0d`, based directly on verified main `15904a75be16e45aab18d779172805f1fb7c8bf0`. Python syntax compilation passed locally. The full pytest suite, mypy baseline ratchet, lint matrices, FastAPI TestClient regression set, integrated resource-to-cognition acceptance, and canonical planning/execution separation passed in hosted CI.

All eight exact-candidate workflows passed: CI 39876012702, Required Quality Gate 39876012648, Release 39876012682, Codex CI 39876012971, Gradient null regression 39876012674, Invariant Tests 39876012776, Docker Image 39876012703, and Lint Benchmark 39876012733. The strict gate passed actual Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate metadata guard.

PR #2649 merged normally as `76c93596d4d714594d9dcac246e86f6943b015af`. Its tree is `c334e2c0a225843910f1c8cb406b607d667fce0d`, identical to the candidate tree, with verified main `15904a75be16e45aab18d779172805f1fb7c8bf0` as first parent. No production goal execution or model inference occurred.

Sequence: 596 (verified source integration)
