# Active construction checkpoint

Sequence 149 closes the mismatch between generic-history readiness and a task-family-required staging request. The read-only doctor now accepts the explicit family and returns only exact admitted records named by completed ticks with verified writeback receipts, including their IDs and digests. A nonmatching family is separately reported as awaiting relevant history. Default generic readiness remains compatible.

The positive and negative cases were exercised through actual cognition/writeback owner custody; two focused tests passed and changed Python compiled. Test invokers are deterministic fixtures. No real-model behavior, typing, hosted CI, or production verification.

Latest source commit: d20cc8bafb162484f4e6d061e908b146ed4f6575
Latest source tree: b1ec482c9da738f2ae4cc9b46f1c20b2932b9cdb
Latest segment: work/construction/segments/0149-task-family-doctor-preflight.md
Segment SHA-256: 14c03bbf19c5cc1c4c021f92e91fabd41068ce140860547e423de37097b98cd8
Evidence: work/construction/evidence/0149-task-family-doctor-preflight.json
Evidence SHA-256: d9c86879023914aeddd98934ee031d59f221a2320d96311d3f8c669a69a0bdd0
Sequence: 149

Next: inspect exact source-task, evaluator, score, and World-State bindings for the task-family episode and identify any remaining provenance gap before attempting real POSIX model serving. Real model file custody and authorization remain external.
