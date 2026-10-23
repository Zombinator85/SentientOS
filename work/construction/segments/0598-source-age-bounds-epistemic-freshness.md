# Sequence 598 — source age cannot be upgraded to current freshness

PR #2653 adds an adversarial regression at the source-to-epistemic-adapter boundary. It presents a runtime observation recorded three days before the builder clock while declaring the source posture `fresh`. The world-state builder computes the source as stale from event age, and the epistemic adapter binds that stale posture while preserving the exact observation time and source digest.

Existing controls remain: a current serving observation stays current, an observation without a trustworthy time remains unknown, and the state owner’s canonical-planning recovery test keeps stale-only support review-required. No production code or freshness policy changed; the increment locks the existing no-upgrade behavior into regression coverage.

The exact source candidate is `0696a5231a8ad9c724221cca91aba0b828c9008f`, tree `eb2efd3212dcfb0d4e0dcf7e9d9b045466991b38`, based on verified main `61c982402cfd5ed2dd23ba05e499a2bf0924feb1`. Python syntax compilation passed locally. Hosted pytest with coverage, the mypy baseline ratchet, source validation, and the integrated resource-to-cognition lifecycle passed.

All eight exact-candidate workflows passed: CI 39880532343, Required Quality Gate 39880532337, Release 39880532303, Codex CI 39880532363, Gradient null regression 39880532314, Invariant Tests 39880532359, Docker Image 39880532341, and Lint Benchmark 39880532313. The strict gate passed actual Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate metadata guard.

PR #2653 merged normally as `bb672aa05d6a82b894ebadbfcb7b7252fb133cc4`. Its tree is `eb2efd3212dcfb0d4e0dcf7e9d9b045466991b38`, identical to the candidate tree, with verified main `61c982402cfd5ed2dd23ba05e499a2bf0924feb1` as first parent. No model inference, production model transition, or goal execution occurred.

Sequence: 598 (verified source integration)
