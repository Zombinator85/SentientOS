# 0092 — Carry self-model qualifiers into the ordinary cognition prompt

Source baseline: `4d77a93f05815598642b1a0a9cdc923bc36e045b`, tree `408b5416736002aaf4968510367d2e5a109ac8a2`. The resident cognition prompt previously identified prior self-model only as an earlier evidence-bound representation. It now explicitly directs ordinary cognition to retain claim category, stage, temporal scope, status, freshness, source observation-time metadata, current-truth, interpretation, and authority as binding qualifiers; historical or unknown evidence cannot become current through retention or reconstruction.

The new qualifier is appended only to the ordinary cognition prompt when a prior self-model is composed. The shared `EXPERIMENT_CONTEXT_INSTRUCTION` constant remains unchanged because historical preregistered experiment protocols bind its digest. Integration coverage constructs a historical developmental-trial claim, sends it through the actual cognition request, and verifies the exact N+1 projection plus qualifier language in the prompt.

Six focused developmental modules passed **151 tests, 0 failed, 0 skipped**. Changed Python compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0092-self-model-consumer-qualifier-junit.xml` and `work/construction/evidence/0092-self-model-consumer-qualifier-results.json`.

This verifies prompt composition and custody, not local-model compliance or learned behavior. The actual local-model acquisition/transfer demonstration remains blocked by missing model payloads, commissioned identity, and exact time-bounded approval. No model was loaded or invoked.

Next: audit authored lesson packets for provenance separation: historical self-model interpretation may inform a later uncertain lesson, but must not be copied as current evidence or represented as an independently admitted fact.
