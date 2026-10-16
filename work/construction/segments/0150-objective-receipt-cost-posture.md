# Sequence 150 — Preserve objective receipt and cost posture

Base source: 3cc0a671087cb16b51e1a6ae08a849875a70bf8d, tree e2a6fb2fa099209c9fe7c3a7793fe2fb1ee081e4. Tested source: 9e20c2fa2a906b7b18f97f791f2fadaae1c3e4f6, tree 009ca1147ae0cb8a684f99a3c53c241f33f71100; published by expected-HEAD CAS and independently read back with all changed blob identities.

The objective result inspector previously mislabeled the preregistered `max_output_chars` as output bytes. It now preserves that request as a character bound, and reports `output_size_bytes` only when it is a bounded integer in the verified invocation receipt. Condition and progression records retain exact inference receipt identities, bounded output/truncation and backend-reported completion posture, and resource allocation/attempt/consumption-link identities when the historical observation binds them to the verified receipt. A mismatch fails closed.

Receipt linkage is explicitly not ledger reconciliation. The result path reports CPU, GPU, energy, and generated-token values as unknown and records that ledger reconciliation was not performed. This avoids presenting requested budget, output bytes, or invocation linkage as measured resource consumption.

Changed Python compiled. Three focused tests passed: the explicit objective request path, receipt-bound multi-episode progression/restart inspection, and the resource-linkage negative control. The tests use deterministic fixture inference; they do not establish actual model learning, real resource consumption, typing, hosted CI, or production behavior. Documentation now states these semantics.

Next: trace task-family examples and evaluator/source identities through the exact task descriptor, scored run, and next-tick World-State feedback. Identify whether the retained result contains enough source lineage for useful subsequent task selection without exposing the private oracle; then continue into the next concrete gap.
