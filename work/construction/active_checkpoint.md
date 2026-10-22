# Active construction checkpoint

## Current verified state — sequence 585

Sequences 582–585 establish and test deterministic least-generation-first epistemic service, including a same-tick restart with highly unequal active-binding counts. The omitted proposition's durable binding set remained unchanged; after owner reconstruction, the less-advanced proposition was selected despite a seven-to-one evidence-volume imbalance. PR #2626's exact candidate passed all eight hosted workflows, including strict Administrator audits, finalization, the separate metadata guard, source validation, and the 143-pass CI suite. Sequence 584's append-only evidence was included in the verified merge.

Latest verified main: `d32135e39ce79b08f41133db50ba92160fa1ab7e`, tree `aabc6d990207f15dbd9a6f6e849a2522a6dc81c3`
Latest construction segment: `work/construction/segments/0585-fair-epistemic-volume.md`
Latest segment SHA-256: `316fde6e34eec32cb2294584fd9d4945b3dffdc0f218ca58c442a5bf4514fc11`
Sequence: 585 (verified source integration)

Next: verify that state generation advances only after a verified durable receipt, including interrupted publication, rejected writes, and recovery. Ensure retry, duplicate snapshots, and omitted candidates cannot be reported as served unless the receipt and successor state are recovered and validated.
