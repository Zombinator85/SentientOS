# Recovery state - sequence 910

Checkpoint format: sentientos.construction_checkpoint:v2
Latest verified main: `49136b5023765afa3f67b97bd3ae64ac67922b11`, tree `2eac22863d8a741ba75c71b35ca6d8d080ce9c32`
Checkpoint binding origin: `1eff1c957da566652011112f6118bd1dc135f01e`, tree `3295e0565ea0a8a33902640e77fc719552b21197`
Previous checkpoint identity: {"bytes": 1086, "git_blob_sha": "ee96e219983177b4fe44db16e026bfa0f46591ea", "path": "work/construction/active_checkpoint_v3.md", "sequence": 908, "sha256": "87d621804043ba53751ad4ee510efdbe9bbb375605f445940e1f6eaeed193c50", "source_commit": "49136b5023765afa3f67b97bd3ae64ac67922b11", "source_tree": "2eac22863d8a741ba75c71b35ca6d8d080ce9c32"}
Latest construction segment: `work/construction/segments/0910-reject-blank-causal-identities.md`
Latest segment SHA-256: `211dbde0493be02b47c05db2e1d2863656bb28cf87a342154965005e591dc961`
Sequence: 910

Recovery: use the v3 immutable predecessor-linked shard chain and the previous checkpoint identity above. Earlier checkpoint bytes remain available in their verified Git parent trees; do not duplicate snapshots.
