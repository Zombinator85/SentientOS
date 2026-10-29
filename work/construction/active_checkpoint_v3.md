# Recovery state - sequence 970

Checkpoint format: sentientos.construction_checkpoint:v2
Latest verified main: `44c54fd19375a799f4a90742a63c8d81c3f682a7`, tree `e594758952aa62a6d616ca6b18d5e2f781fed114`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Previous checkpoint identity: {"bytes": 1117, "git_blob_sha": "290c12da7c386ca9c38a04f9e98540ebf5c42181", "path": "work/construction/active_checkpoint_v3.md", "sequence": 969, "sha256": "959e961f31912e2f14c934ee8057b43ec95cbf64e0790a7c3095373e4f3b46a5", "source_commit": "44c54fd19375a799f4a90742a63c8d81c3f682a7", "source_tree": "e594758952aa62a6d616ca6b18d5e2f781fed114"}
Latest construction segment: `work/construction/segments/0970-merge-pr-3049-and-repair-recovery-test-race.md`
Latest segment SHA-256: `8851a1c59f925d2c0e7ff498e7b2a74078209fdd7a8ebccf18b82c29533553d5`
Sequence: 970

Recovery: use the v3 immutable predecessor-linked shard chain and the previous checkpoint identity above. Earlier checkpoint bytes remain available in their verified Git parent trees; do not duplicate snapshots.
