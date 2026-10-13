# Active construction checkpoint

Sequence 148 records the operator handoff gap in the controlled task-relevance path. The stage API already supports an exact required task family, but the CLI could not express it. The CLI now exposes that option while preserving the existing optional general-history mode. The family string remains a relevance label; staging qualifies it only through completed-tick records with verified writeback receipts.

The focused family acquisition, adverse-history, transfer, and restart/read-only progression nodes passed (4 passed). Changed Python compiled. Fixture-only; no real local-model behavior, hosted checks, typing, or production verification.

Latest source commit: c506037c8bc58ae79d07b71836f9b08643d23fc8
Latest source tree: 3c8b510f9f68288b34eb197fe8c66e8f228addb9
Latest segment: work/construction/segments/0148-task-family-staging-handoff.md
Segment SHA-256: ce09dace6d7940b55d97050c07b0f2e44bd62bb306770014cd4895801cfb9b84
Evidence: work/construction/evidence/0148-task-family-staging-handoff.json
Evidence SHA-256: 3569835bd1fb1861658d9f90282df109772f2f9f868fa0aa030e9dd4c938e6bd
Sequence: 148

Next: teach the read-only host doctor to qualify the selected task family against exact admitted record identities/digests before staging, then continue toward a source-backed outcome from a real supported host episode. Keep the daemon and all commands within one POSIX installation/custody root.
