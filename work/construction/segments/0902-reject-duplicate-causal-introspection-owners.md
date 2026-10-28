# Sequence 902: reject duplicate causal-introspection owners

A reproduced validator gap allowed one valid owner projection to appear twice in a snapshot after the projection inventory and snapshot digest were recomputed. Duplicate entries could then be presented downstream as multiple independently attributable owner reports. Snapshot validation now requires owner IDs and projection IDs to be unique, matching the capture runtime's unique-registration contract. The regression re-digests the duplicate snapshot and verifies fail-closed rejection.

Candidate implementation: `07699fa4079fe4c9109d12bda52da401550764a9`, tree `a9287250b5ef38b9f7a2ca1bf44e222831d9201e`, based on verified main `026e523f4303e1beaf69c771aed680db36b7c7bb`, tree `2231c33651da79db098fc2340ba136d0ac120333`. Focused causal-introspection, composition, and runtime-closure tests passed 75/75 with zero failures or skips; mypy passed; the documented docs extra built 617 pages. Hosted acceptance remains pending for the combined candidate.

Evidence record: `work/construction/evidence/0902-reject-duplicate-causal-introspection-owners.json`.
