# Sequence 492 — bind goal allocation bytes to persisted plan evidence

## Allocation identity continuity

The canonical daemon planner already consumed the recovered prior epistemic projection and retained positive and adverse historical outcomes. Its persisted plan evidence named the selected allocation artifact by path, but did not identify the artifact's exact bytes. A replaced file could therefore be mistaken for the allocation that informed the plan.

PR #2486 adds a SHA-256 digest over the exact canonical allocation bytes, binds it into deterministic plan identity and persisted plan evidence, and exposes it in read-only daemon feedback, including empty or deferred plans. Persistence and readback verify the linked artifact's bounded regular-file contents against the digest. Historical plan evidence without the field remains readable. The regression checks retry identity, positive historical planning, model-identity drift, malformed digests, and rejection of allocation substitution. Planning remains non-authorizing and execution-free.

## Verification and merge

Candidate `f522ff3a25cc901d4e817f31b5169d9f9c82ec7e` (tree `04ad88a8f5a002e10409f721c3f5f0947dc7ebe8`) was based on verified main `124de0f9ced349de7342901a2e1338c460c05a00`. The affected planning, progression, evidence-bound, resource-learning, and model-lineage suites passed; compilation and diff checks passed; the repository Mypy ratchet reported zero new errors. Exact candidate Quality Gate #39398069534 and all hosted candidate checks passed, including the hosted Administrator audit, immutability, acceptance, and metadata-guard steps. Candidate tree and all five changed source/test blobs were independently read back from GitHub.

PR #2486 was merged by regular merge as `2adf59db661779ba8d62d5d8417381f442fdbaf0`, with tree `04ad88a8f5a002e10409f721c3f5f0947dc7ebe8` and ordered parents `124de0f9ced349de7342901a2e1338c460c05a00` and `f522ff3a25cc901d4e817f31b5169d9f9c82ec7e`. GitHub reports a valid signature; independent main readback confirmed the exact candidate tree and changed blob identities. The post-merge Quality Gate, CI, source validation, Mypy, docs, Helm, Docker, CPU smoke, and invariants passed. Forge Smoke was skipped by workflow condition.

## Operational observations and next dependency

At 2026-10-20T09:20:24Z, no scheduled Federation Health run on current main `2adf59db661779ba8d62d5d8417381f442fdbaf0` was observable. The latest scheduled run, #8680 (`39378086813`), ran on older head `800dcef026b32c45c5668282b260ca2e39ab4c24`. Its Administrator preflight and health/report job succeeded, and artifact #12243819144 independently bound report digest `e16a5a4ac85b5c0f3dead86466a0fc6666b47e23b7e1bca2b0689527d0ceb3e9` to that older head. The separate publisher failed because repository policy denies Actions-token pull request creation. Nightly Audit Integrity #501 (`39396388332`) passed on `124de0f9ced349de7342901a2e1338c460c05a00`; the latest Nightly Self Check #507 (`39235681245`) passed on older head `b5912ecc8f25cebcb5338f623bae8d829261f6ce`. Neither establishes scheduled execution on current main.

Next, carry the exact plan-bound allocation identity through the executor boundary. Verify that a mismatched or replaced allocation cannot begin a task or create execution-journal evidence, while retaining legacy evidence compatibility and the existing execution authority checks.
