# Active construction checkpoint

Seq236 verifies the configured campaign-selection path: the runtime reads the digest-bound explicit selection, reconstructs a read-only owner, and includes only those selected histories in admitted signal evaluation. Selection tampering fails closed without fallback discovery.

Latest source commit: 0df408435dd8a7cd96a462ecd5a586eeb4a532d8
Latest source tree: 3a9220c7b24c081f018d7a04e1fa72b5817474a0
Latest segment: work/construction/segments/0236-explicit-campaign-runtime-selection.md
Evidence: work/construction/evidence/0236-explicit-campaign-runtime-selection.json
Queue: work/construction/reconciliation_xvii_queue.json
Sequence: 236

Validation: three focused nodes passed, affected tests compiled, and `git diff --check` passed. Campaign source issuers remain unverified; no effect authority was added.

Next: continue the runtime temporal/recovery tests, the later bounded maintenance proposal path, and the still-open resource, epistemic, goal, and strategy programs.
