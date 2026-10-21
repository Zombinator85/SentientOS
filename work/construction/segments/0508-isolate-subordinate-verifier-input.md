# Sequence 508 — isolate subordinate verifier input

Sequence 507's local test count was recorded as 97 after misreading intermediate progress output. A JUnit recount of the exact command against the same source tree found 85 tests, 0 failures, and 0 skips. The append-only sequence 507 evidence is preserved unchanged; PR #2515's description was corrected to 85. Sequence 507 merged as `814f3a4a58b697a7992e4247c988a8aff74a2890`, tree `e6a59f770cdeab6f7ca1a025a4bb6588070d7e78`, with ordered parents `564bff002c4bd0a679bfa8347c0478b1698e0a2d` and `575e0ba79b73fda5f81b9a489205052f17b385bd`. Exact candidate hosted checks, separate metadata guard, Administrator audits, immutability, and post-merge checks passed.

Sequence 508 closes a mutation gap between authenticated subordinate approval binding and controller consumption. The runtime snapshots packet approvals before verification, gives the verifier an independent deep copy, and retains its own execution snapshot for controller context. A regression mutates nested verifier input and confirms the controller still receives the original approval. The exact regression and workflow contract were added to source validation.

Supplemental local verification passed 86 affected tests with 0 failures and 0 skips, targeted canonical Mypy for the changed operator, compilation, workflow YAML parsing, diff checks, and construction custody over all 507 predecessors. The local full Mypy baseline remains unavailable under the sanitized environment; hosted exact-candidate verification is pending. The sequence 508 source commit is `28ba679e5c4a8921e1f2e7e561e1b0d78db198c9`, tree `4064bd7a559c4aef5f116f621071f805a05c8377`, based on verified main `814f3a4a58b697a7992e4247c988a8aff74a2890`.

No production transition, activation, serving, inference, or writeback was performed.

Verified main: `814f3a4a58b697a7992e4247c988a8aff74a2890`, tree `e6a59f770cdeab6f7ca1a025a4bb6588070d7e78`
Implementation source commit: `28ba679e5c4a8921e1f2e7e561e1b0d78db198c9`, tree `4064bd7a559c4aef5f116f621071f805a05c8377`
Sequence: 508 (candidate pending hosted verification)
