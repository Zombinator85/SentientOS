# Sequence 341: bind the omitted resident history complement

## Source increment and integration

Transition context now carries a deterministic count and canonical digest for the exact complement of the selected historical records within the verified resident boundary. It preserves both the selected set and omitted set, and rejects substituted or incomplete boundary/receipt bindings before inference. The frozen A/B protocol identity remains shared across both roles; historical positive and adverse outcomes remain in the boundary. No protocol-bound history is discarded and no production transition authority is granted.

Candidate `398f368bf832e940ff3eccbbeae177d3ba3d4e41` (tree `156ee1d99b06d81c21cb40a0a166e59f15a3d9b4`) merged normally through PR #2331 as `7f026f6ec41190cf3d24c1586f318b8abbebe8a4`, preserving parents `ebbaa6fa447f30f9ef6bd9254c853d64149bec88` and `398f368bf832e940ff3eccbbeae177d3ba3d4e41`. Main tree is `156ee1d99b06d81c21cb40a0a166e59f15a3d9b4`.

## Verification

Candidate CI, lint/Mypy, Docker, invariants, Release, Gradient, Codex CI, and privileged Required Quality Gate passed. Candidate QG run `39083947379` executed 29/29 nodes with zero failures or skips; Administrator UID 0, strict audit, and immutability audit passed. Its artifact and finalizer were independently read back; the finalizer returned `ready_for_pr_metadata`.

Post-merge CI `39084255820`, QG `39084255775`, Docker `39084255940`, invariants `39084255822`, Codex CI `39084255797`, and Docs Deploy `39084255719` passed on exact main `7f026f6ec41190cf3d24c1586f318b8abbebe8a4`. Post-merge QG artifact `12120455500` independently verified source binding, Administrator UID 0, strict and immutability checks, and 29/29 passing exact nodes. Forge Smoke `39084255757` was skipped by configured workflow conditions. A follow-on main CI and invariants pair `39084793851`/`39084793861` was also observed running and is not counted as required evidence here because the corresponding push reran after this main verification snapshot.

The scheduled Federation Health execution recorded in sequence 340 remains the latest observed scheduled run. Nightly Audit and Nightly Self Check still await their next schedule after main advanced; their privilege and least-write requirements remain unchanged.

## Next dependency and evidence boundary

Sequence 342 binds the complete developmental history boundary to the writeback owner's read-only verified record/receipt pairs, failing closed when custody is incomplete. PR #2332 is open as draft; local integrated verification passed and hosted checks are pending. No production A→B→A run, running-source observation, or model improvement is claimed. The stale sequence-178 workspace and sequence-286 provenance-loss evidence remain preserved.
