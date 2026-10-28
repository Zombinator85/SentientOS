# Sequence 904: require causal-introspection owner identity

A provider registered with an empty owner ID was accepted, and its anonymous projection flowed into later World-State. Projection validation now requires nonempty owner ID and owner kind, and runtime registration rejects empty owner and provider IDs before capture. The regression covers both projection validation and registration.

Candidate implementation: `cabccf8e3ffd2ba7f7757ce496cbdf0d4daced31`, tree `9d499eeb14141ac1e5bdec570f125c1d8d75f834`, based on verified main `ed13a22862595dc8c9a725f6c1f055aadb82eaab`, tree `cf30bf07ed350ceec6f7e48f627811aaaad1aae3`. Focused causal-introspection, composition, and runtime-closure tests passed 76/76 with zero failures or skips; mypy passed; the documented docs extra built 617 pages. Hosted acceptance remains pending for the combined candidate.

Evidence record: `work/construction/evidence/0904-require-causal-introspection-owner-identity.json`.
