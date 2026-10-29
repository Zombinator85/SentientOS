# Recovery state - sequence 1001

Checkpoint format: sentientos.construction_checkpoint:v2
Latest verified main: `adbfd341128f954e1e27ebba7dd67ed50b6e1bc0`, tree `47213785be22c837e64c197299236f24a332b999`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Previous checkpoint identity: {"bytes": 1134, "git_blob_sha": "607f586dd6ef42a595463f28fdcee9542ac4a949", "path": "work/construction/active_checkpoint_v3.md", "sequence": 1000, "sha256": "d8572f670b0868e617223b301a78d7d64d7596907d603510a3a43f9979742d86", "source_commit": "adbfd341128f954e1e27ebba7dd67ed50b6e1bc0", "source_tree": "47213785be22c837e64c197299236f24a332b999"}
Latest construction segment: `work/construction/segments/1001-align-mypy-ratchet-lock-runtime-requirements.md`
Latest segment SHA-256: `3d07ad8b893dbeb5ad6eea50bfc3a404d5f96615d56fff2215503c19b104afd8`
Sequence: 1001

Recovery: use the v3 immutable predecessor-linked shard chain and the previous checkpoint identity above. Earlier checkpoint bytes remain available in their verified Git parent trees; do not duplicate snapshots.
