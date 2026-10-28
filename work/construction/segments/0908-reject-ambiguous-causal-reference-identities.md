# Sequence 908: reject ambiguous causal-reference identities

A causal-introspection projection accepted a duplicate reference identifier tied to different digests and source owners. It also accepted malformed reference inventory fields. Projection validation now rejects duplicate IDs across both inventories and rejects unknown kinds, empty IDs/relations/owners, non-SHA-256 digests, and foreign schemas. Regressions cover conflicting identity reuse and malformed fields; the topology document records the identity contract.

Candidate implementation commit: `6771530bc8ba0c407677ff5d11cb9eb9f850df66`, tree `95e87d67c7f7e23dbaa0d0679b04f84e795515f8`, based on verified main `56d5c7882e17f61a609e47a72fef3e821dffc75b`, tree `dce2d015c3855f51b1eca8671a155ae9196a50ea`. The focused causal-introspection, composition, and runtime-closure suite passed 79 tests; targeted mypy, documentation dependency check/build (617 pages), and `git diff --check` passed.

This is an `[untested]` construction increment. The complete regression suite was interrupted after reaching 39% when a dashboard TestClient startup stalled; an isolated startup reproduction also stalled, and no full-suite pass is claimed. Local `verify_audits.py --strict` and `scripts/audit_immutability_verifier.py` were denied with `Access denied: run as Administrator to reach protected memory and policy state.` No privilege gate was weakened. Require exact-candidate hosted Required Quality Gate and CI before merge.

Evidence record: `work/construction/evidence/0908-reject-ambiguous-causal-reference-identities.json`.
