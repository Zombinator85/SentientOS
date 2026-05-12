# Federated Improvement Local Variant Artifact

The federated improvement local variant artifact is a deterministic, metadata-only
record produced by a receiving node when it **derives a local variant** from an
incoming federated improvement candidate under local custody.

This artifact explicitly documents lineage-preserving adaptation, not adoption.
It proves the original candidate was not adopted as-is and the local variant is
also not adopted, installed, applied, merged, routed, scheduled, remotely
executed, or production executed.

The artifact stores only ids, digests, statuses, booleans, compact posture labels,
reason codes, gate codes, warning/risk codes, and lineage refs by id/digest.
It forbids prompt text, raw patch bodies, executable payloads, secrets,
endpoint/client/runtime handles, and provider/network/export authority markers.

A local variant may inform future local work, but any conversion into a new local
candidate remains a separate explicit local governance gate and is outside this
artifact's authority.
