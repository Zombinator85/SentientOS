## 2026-10-13 checkpoint — use production installation receipt recovery in the held-out child

- Continued from freshly verified source commit `2b2ae568dfb03a14870fcd3cb29dd200830c557f` / tree `d7b89eba9430202ce5c1a2896884d7e2eb73751d`.
- Replaced the custom serialized-receipt sidecar in the second held-out episode with installation-scoped receipt custody. A deterministic fixture issuer writes canonical invocation receipt artifacts under the test installation root; the child process constructs a separate invoker and delegates historical receipt verification to the repository's `ResidentCognitiveInvocationReceiptReader`.
- Serving session and witness custody are explicit test fixtures. The child does not inherit the parent invoker, receipt map, or owner. It reads staged request, developmental history, admissions, and persisted invocation artifacts from durable roots.
- A separate staged task is used for tamper rejection. The test alters one persisted experiment receipt's request digest, starts a fresh child, and confirms canonical receipt reconciliation rejects the run before any new invocation; it restores the fixture artifact afterward.
- The fixture again yields present/withheld/restored correctness 3/3, 0/3, and 3/3. The owner reports receipt-bound invocation as verified because the test fixture publishes canonical receipts. That status does not establish that a real local model ran or acquired competence.

Checks on published source:
- Focused fresh-process transfer, current-context isolation, adverse-example and progression group: 4 passed.
- Compilation and UTF-8/NUL/trailing-whitespace checks passed.

Source commit: eb89f0e942ed5fa408b68be9caeb996f2817c4f8
Source tree: 7d4c17c852ba30555ce3681d988be2ef8a437cd0
Changed test blob: 88e0342e9f31864ef792a17949ca7a8bf9a9d603
Construction remains unverified for production.

Next: investigate the evidence contract behind `actual_nonsynthetic_inference_verified`. Determine whether the authenticated serving and invocation custody actually distinguish a fixture issuer from independently observed local-model execution. Preserve the distinction in source and experiment outputs before attempting actual acquisition/transfer.
