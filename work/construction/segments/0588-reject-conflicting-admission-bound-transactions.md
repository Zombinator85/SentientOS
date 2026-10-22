# Sequence 588 — reject conflicting admission-bound transactions

PR #2632 adds an exact source-validation regression for two individually well-formed durable transactions that claim the same state generation but carry different mutation admission bindings. Owner reconstruction rejects the generation conflict before it can accept the transaction pair or repair receipts. The regression confirms persisted state, update events, both transaction records, the published state receipt, and the admission ledger remain unchanged.

The first candidate, `7c1904c71063ba924c67fc9efb7f1376fa82897b`, failed source validation (run 39836979777) because its injected transaction record used the default non-private file mode. The next candidate, `cad7973d1c34d1821a26946449da16b596e62239`, failed run 39837724098 because the fixture used the full transaction identifier as its filename; canonical collection custody requires the identifier suffix. The final fixture uses mode 0600 and the canonical filename. No production source or verification rule changed.

Final candidate `ecc068cc112a0dd86d89d71f986962503b39aaf8` passed all eight hosted workflows. CI run 39838195862 reported 143 passed, 13 skipped, zero failed; source validation reported 413 passed, 18 skipped, zero failed, and selected the new conflict regression as a required acceptance node. The strict Quality Gate (39838195900) passed Administrator audits, audit immutability, hosted finalization, and the separate metadata guard. Lint Benchmark, Codex CI, Gradient, Release, Invariants, and Docker also passed. Source-validation checkout `afcca6b8d39cda8bab01e55a16203ad74cbdfce7` has an identical tree to the candidate.

PR #2632 merged normally as `1139e3117adf54c3529555d9d2faf2befc55cac2`. GitHub's candidate-to-merge comparison reported no changed files. The merged tree is `ca41cbc5fe13458fd2c62ce414d7ad8268f070d8`.

No inference or production transition occurred.

Sequence: 588 (verified source integration)