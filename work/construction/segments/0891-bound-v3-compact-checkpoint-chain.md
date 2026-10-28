# Sequence 891: bound v3 recovery checkpoints

The v3 continuation root now anchors a compact checkpoint chain to the verified sequence-890 checkpoint. New checkpoint transitions are immutable shard data, linked by exact checkpoint identities and evidence; old checkpoint bytes remain available in the original Git history. Candidate preflight verifies each predecessor against its recorded source commit and tree, including ancestry and exact Git blob identity.

Local focused construction suites passed (53 tests), targeted mypy passed for both changed verifier scripts, and `git diff --check` passed. The documentation build remains pending the exact-candidate hosted Required Quality Gate, whose Administrator bootstrap and pre-commit finalizer perform the docs dependency check and build. No hosted acceptance is claimed here.

Verified source main: `ae254ab1b04c6dc51ad9e1a726c7ce13d4dde570` with tree `f59e273a5fdc12330bb9162fa1e4d6cc132c7b8f`.
