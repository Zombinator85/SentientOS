# Sequence 292 — Bind every successful completion to its evidence bytes

Sequence 291 made a successfully reconstructed completion proof change the next canonical allocation. Inspection found that only the forge-run check supplied an evidence digest; other checks could return `done` from a catalogued artifact without binding the artifact bytes into the completion identity. Canonical planning could therefore preserve a completion claim without preserving which bytes supported it.

The completion dispatcher now gives every successful non-run check a canonical SHA-256 identity over the goal, check, outcome, progress, reason stack, evidence paths, and exact bytes read from each evidence file. Missing, unreadable, or out-of-root evidence fails closed and cannot defer the goal. Strict schema-v3 forge-run evidence keeps its existing reconstructed digest. The digest is persisted through the existing completion result and downstream allocation/plan evidence; no execution authority or audit exception was added.

The tests cover exact-byte digest changes and fail-closed missing evidence. The six affected suites passed 35/35 with no skips, compilation and diff checks passed, and the full hosted Mypy baseline ratchet passed. Targeted local Mypy still reports nine pre-existing diagnostics in the completion module; hosted CI confirms no new baseline regression.

Local source commit `9d8dadde3550c9f39cd913610dfd6ba87a5c302c` and remote equivalent `e25210212c0e6d57211a8ec69a50e6b56958622e` have identical tree `4d3609cd3478cccd251d16ea73249e0afd082994`. Remote blob readback matched both modified files byte-for-byte. CI `38972842853`, Required Quality Gate `38972842896`, and Invariant Tests `38972842878` all passed on that exact source SHA. Gate artifact `12077563403` read back with the GitHub SHA-256 and records effective UID 0, verified Administrator authority, exact source/tree, unchanged source, strict audit, and immutability.

Sequence 291 is also fully verified: CI `38972626441`, Gate `38972626137`, and Invariant Tests `38972626142` passed; its gate artifact was read back and matched digest `d6a3ae9a07588ec0a6372b36dcbdfa2de3e970e0d4e931a3eb6db310725648a9`. The sequence-290 repair CI `38972248264` completed successfully.

The earlier sequence-286 finalizer cleanup remains an unresolved historical provenance gap: nine known payloads and one unidentified record remain missing.
