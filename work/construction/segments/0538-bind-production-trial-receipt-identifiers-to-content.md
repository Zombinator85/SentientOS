# Sequence 538 — bind production-trial receipt identifiers to content

The production-trial receipt verifier checked the receipt's outer self-digest, posture, and plan reference, but did not require the semantic `receipt_id` used by the writer. A caller could change or omit that ID, recompute the outer digest, and still obtain a verified receipt under an unrelated identity. Verification now recomputes the canonical ID from the receipt body without the ID or outer digest and requires the exact `production-model-replacement-trial-<24 hex>` value produced by the writer. Regression cases cover a missing ID, an arbitrary recomputed ID, and a non-string ID whose outer digest was recomputed.

The receipt regression, its hosted-workflow contract, and the complete production-trial and synthetic rehearsal test files passed locally (25 tests). Targeted Mypy reported no issues in the two changed Python source/test files; compilation, CI YAML parsing, and diff whitespace checks passed. The full hosted candidate checks and privileged Quality Gate are pending. The canonical continuation custody verifier passed for the prior 537 segments before this append.

Sequence 537 merged normally as PR #2546. Merge commit: `500fd87c0d807f9ef2128902c166d04c3203f8fc`, tree `7bc937225377b689657cd52df96cbb604ccc2639`; parents `5b9f7b43bbed42ac2fed43f9db4a73ba427923bc` and `137ff7dd72ab2ef95a74a20651d517ba25495056`. Exact-candidate hosted CI, Mypy ratchet, integrated lifecycle, docs, Docker, invariants, Release, Codex CI, Lint Benchmark, Gradient null regression, and the privileged Quality Gate all passed. The Quality Gate's source-bound finalizer and pre-publication metadata guard passed. Post-merge workflow runs had not yet appeared when this evidence was prepared.

Verified main: `500fd87c0d807f9ef2128902c166d04c3203f8fc`, tree `7bc937225377b689657cd52df96cbb604ccc2639`
Implementation candidate: `abcb6ccd7b81d15c6ab3c69fb6c0fedeeacd4b5b`, tree `343687128774739c699b7ed2a2fb22c44c6c58f7`
Latest construction segment: `work/construction/segments/0538-bind-production-trial-receipt-identifiers-to-content.md`
Sequence: 538 (candidate pending hosted verification)

No production model transition, activation, serving, inference, or writeback was performed.
