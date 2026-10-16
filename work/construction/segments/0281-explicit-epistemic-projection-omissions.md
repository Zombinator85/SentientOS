# Sequence 281 — Preserve explicit omitted epistemic positions

Starting from verified main `b181e4d7de7ddcf46aab37bf7f325d2e21e2a5ba`, this increment addresses an information loss at the persistent epistemic projection boundary. The owner selected prior states deterministically, but states beyond the configured bound had no identity in the projection. Canonical planning could therefore confuse an omitted proposition with a proposition that had no prior state.

Meaning-bearing projection v3 now carries a bounded manifest for every omitted latest state: proposition, state and update-event identity; generation and tick; stance, freshness and dependency posture; and a digest over the ordered omission rows. The projection source tick includes the newest event even when it belongs to an omitted state. Validation rejects malformed, reordered, duplicate, selected-overlapping, untimestamped, or digest-substituted omission records. The existing v2 shape remains unchanged when nothing is omitted.

Planning treats an explicitly tagged omitted proposition as unresolved and retains its exact omission identity in canonical work-plan evidence. Cognition passes the projection manifest in the complete prior context so the source projection digest and inference prompt digest bind both delivered positions and owner-level omissions. Omitted positions remain prior evidence only and carry no truth or authority.

The affected local verification passed 115/115 epistemic, cognition, and plan-only tests; privileged-wrapper unit tests passed 3/3; compilation and diff checks passed. Local runner records identify stale HEAD `d8d7a219221cd94240accf7991fe353b14f6a84e`, so these runs are exploratory. Exact candidate verification is pending hosted PR checks.

The already-merged hosted privileged path was independently checked on main: Required Quality Gate run `38955380278` executed strict audits and immutability as effective UID 0 against exact commit `b181e4d7de7ddcf46aab37bf7f325d2e21e2a5ba` and tree `4b5d15360c3b3208c6906f9f6ba7c17b16fc2e71`. The uploaded artifact reports both commands exit 0, unchanged source and repository identity, and passed status. Downloaded artifact SHA-256 matches GitHub's recorded artifact digest.

Next: carry the omitted event identities through a later post-reconstruction scoped decision and verify that an omitted prior state can only trigger review, while a subsequent complete projection can resolve applicability without dropping positive or adverse outcomes.
