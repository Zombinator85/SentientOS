# Sequence 152 — Reuse admitted task-family history across model succession

Base source: 2d4ab864d03ce77c63207b02f2322d3c95864242, tree 8bb6868e019af8ec56140ca06b1053ed27f1d645. Tested source: 755fc80847edd6140849fa2aef64a3a9903a6de6, tree b9fd0584becbe72e432c360a27a420b3c42bd5b1; published by expected-HEAD CAS and independently read back.

Extended the end-to-end task-family integration case through the existing model-replacement owner. It obtains the admitted source record through `FrozenCausalContext.create_from_admitted_history`, which rechecks completed records and writeback receipts, then freezes the exact record ID/digest and bounded candidate content. The same evidence is visible in the history-present A and B fixture prompts; withheld prompts contain no developmental-history rows, and current evidence remains a separate projection.

A child process reopens the read-only model-replacement artifact store and verifies the persisted context identity and exact history record IDs/digests. Reconstructing the replacement owner from that persisted context reuses the completed trial without additional endpoint calls. This proves process-level context-manifest recovery and no-replay for the fixture experiment; it does not prove a real successor process loaded or learned from model weights, nor real A/B performance.

The exact integrated owner test passed (1 passed, 61.14s) and the changed test module compiled. Documentation now describes the existing admitted-history factory and its limits. Endpoints are deterministic fixtures; no production, real-model, typing, or hosted-CI verification.

Next: determine whether a real model-host run can be authorized and supplied by existing custody, without repeated searches or fabricated approval. If unavailable here, continue the next source-supported score-feedback/retrieval seam and preserve the external dependency precisely.
