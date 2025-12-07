# Vow Digest & Version Consensus Primitives

These primitives provide deterministic, side-effect-free helpers for hashing the
canonical vow text and comparing digests between peers. They intentionally avoid
network communication, scheduling, and any self-modifying behaviors so that
higher orchestration layers can safely compose them.

## Vow digest
- `vow_digest.compute_vow_digest(text: str) -> str`
  - Hashes UTF-8 encoded text using SHA-256 and returns the hex digest.
- `vow_digest.load_canonical_vow() -> str`
  - Reads the immutable local resource at `resources/canonical_vow.txt`.
- `vow_digest.canonical_vow_digest() -> str`
  - Convenience helper that loads the canonical vow and returns its digest.

## Version consensus
- `version_consensus.VersionConsensus(local_digest: str)`
  - Initialized with the local canonical digest.
- `compare(peer_digest: str) -> dict`
  - Returns a structured dict containing both digests and a `match` flag.
- `is_compatible(peer_digest: str) -> bool`
  - True when the peer digest matches the local digest.

## Integration hook
`sentientos.consciousness.integration` exposes a pre-wired `vc` instance built
from the canonical vow digest. It is present only for higher-level coordination
layers to consult; no automatic enforcement, network lookups, or scheduling
occurs at this layer.
