# 0141 — bind history retrieval policy to its family and protocol

- Continues from verified source `4d58ea80244714fee5564f1a8b44be31e36b395b`, tree `3cb63df4aa7a97bc1b04e4253f224b38b6a39d28`.
- The v6 selector validator now rejects a task-family policy without a task-family identity and rejects a recency-only policy when a family selector is present.
- The canonical experiment summarizer reconciles each v6 observation’s available record IDs/digests and family identity to the preregistered protocol. The withheld arm remains over that same eligible history set while receiving none of it in the model prompt.
- Focused tests: the family acquisition/transfer and receipt-substitution pair passed (**2 passed**); the family path, fixed-context present/withheld/restored comparison, and canonical summarizer compatibility group passed (**3 passed**). Changed Python compiled. Targeted mypy reports 15 existing cognition diagnostics; no new selection-binding diagnostic. No full suite was rerun after this small increment; no real model behavior is established.
- Evidence: `work/construction/evidence/0141-history-policy-protocol-binding.json` (SHA-256 `351cc0452677a1cb1dead437730a03c66dfb878cd498d5d2798a03c1d674b161`).
- Next: carry exact invocation-linked resource allocation, attempt, and consumption-receipt identities into cognition observations and controlled experiment records where the existing verified invocation receipt provides them; preserve genuinely unlinked historical invocations and report unavailable measures as unknown.
