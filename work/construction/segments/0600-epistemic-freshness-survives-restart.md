# Sequence 600 — epistemic freshness and withdrawal survive restart

PR #2657 extends the sequence 599 freshness lifecycle across a persistent-owner restart. After a current source observation is revised to stale, the test reconstructs the epistemic owner and mutation controller, verifies the durable receipt chain, and replays the same stale snapshot. The replay appends no evidence and advances no state; the stale binding remains the only active record and the proposition remains suspended.

The recovered runtime then admits an explicit evidence withdrawal. Replaying the unchanged source snapshot still leaves active membership empty, while both the original current record and its stale revision remain in append-only history. This checks that owner reconstruction cannot revive withdrawn history.

The exact candidate changed only `tests/test_resident_epistemic_development.py`. The relevant production modules and dependencies were compared byte-for-byte with the exact main source. Local focused verification passed 29 tests, Python syntax compilation, and targeted mypy for `resident_epistemic_development.py`.

Candidate `312c0a013a48714e46417af8917039a9c83b300b`, tree `d88e8d2ceb284870523c2b4a22849265c638de77`, parent verified main `1f6fecd942cfab70c0ea59964ff870a7cfd9cf8f`. All exact-candidate hosted checks passed, including Required Quality Gate `39886221565`, source validation, full self-check, documentation, Helm, invariants, gradient-null tests, lint matrix, build, and CPU smoke test. The gate passed strict audits with actual Administrator authority, exact acceptance binding, hosted finalization, and the separate pre-publication metadata guard.

PR #2657 merged normally as `d9565001d4e9a63fae4d368fe29f9b8535ce6b83`, with the exact candidate tree and verified main `1f6fecd942cfab70c0ea59964ff870a7cfd9cf8f` as first parent. Post-merge checks on the final main `a70c8b4a75e84f1fb8ee7a4ae9511c86f49f8825`, tree `684f8b5e83e7010707d13f2916dfd2d319249448`, all passed: source validation, full self-check, docs, Helm, invariants, builds, CPU smoke, deploy, and Required Quality Gate.

The same final main includes merged operational receipt PR #2639 for scheduled Federation Health run `39871453383`. The GitHub App token and publisher created the report-receipt PR; its hosted checks and finalizer passed, and it merged normally. The bound report says `stale`, zero events in 24 hours, and explicitly identifies the tracked local snapshot as not live telemetry. No freshness was fabricated.

The transition recovery boundary was also reviewed without executing a production transition. The signed operator request is verified before journal reconciliation; recovery binds the request digest, requested stage, and approval digest to the durable attempt and terminal entries, then publishes a receipt without replay. The exact-main transition-operator suite passed 47 tests, and a local expiry-window simulation recovered completed and interrupted journal cases with `effect_performed=false`. No bypass or source defect was found in this boundary.

Sequence: 600 (verified source integration)
