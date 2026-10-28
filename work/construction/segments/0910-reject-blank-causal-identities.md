# Sequence 910: reject blank causal identity fields

The causal-introspection validator rejected empty owner, capture-tick, reference-ID, relationship, and source-owner values but still accepted strings containing only whitespace. It now rejects those blank identity values before projection publication. The regression preserves meaningful nonblank values and tests the exact fail-closed cases; the topology guide and exact-node acceptance manifest describe the boundary.

Candidate implementation commit: `eba978d317f80e52c784f693e863e717438438fd`, tree `631a34f3ce7d032f6ebc30d8314c3b9c2d6134eb`, based on verified main `49136b5023765afa3f67b97bd3ae64ac67922b11`, tree `2eac22863d8a741ba75c71b35ca6d8d080ce9c32`. The causal-introspection, composition, and runtime-closure regression set passed 80 tests with zero failures or skips. Exact task acceptance passed, targeted mypy passed, the documented MkDocs build generated 617 pages, and `git diff --check` passed.

This is an `[untested]` construction increment because the exact candidate has not yet passed hosted Required Quality Gate and CI. No production-readiness claim is made. Administrator checks, custody, authority boundaries, and effects were not weakened.

Evidence record: `work/construction/evidence/0910-reject-blank-causal-identities.json`.
