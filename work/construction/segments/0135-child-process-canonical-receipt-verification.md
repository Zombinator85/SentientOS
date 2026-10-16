# 0135 — verify child recovery through installation receipt custody

- Continues from exact remote source `93441a4bc6632ea08110d3e8d9a4c3b4d60a59ab`, tree `e4e670268955f08ac47604fac3ebfd8484eb6e44`.
- The interrupted scored-family recovery test no longer substitutes a test-local receipt verifier in the child process. It reads fixture-issued invocation receipts and the serving-session witness from an explicitly rooted installation, then calls the real `ResidentCognitiveInvocationReceiptReader` over its read-only installation view.
- A positive child reconstructs and verifies the interrupted score without changing installation custody. An adversarial second child rejects a substituted request digest in a persisted invocation receipt through the same reader; the original inference call count does not change.
- Focused developmental suites: **164 passed, 0 failed**. Changed Python compiled. The source records remain fixture-generated and do not demonstrate actual model behavior or acquired competence. Untested for production.
- Evidence: `work/construction/evidence/0135-child-process-canonical-receipt-verification.json` (SHA-256 `522932f06149aef0d3032956185a46c324c6b7418c0cf6e2e5ba28d28868418c`).
- Next: exercise the crash boundary after a recovered objective run is durably available but before its World-State projection is consumed by normal developmental writeback; verify repeat projection and post-restart admission remain idempotent and answer-safe.
