# Active construction checkpoint

## Latest verified main

PR #2386 regular-merged sequence 416 at `1ee81c45efcc0565ea294944707e725ffaad3b6c`, tree `d2ae2319b22a1c38fbe25178d525436e1c21dde3`. Candidate `8b9cbc2c438e0b789c160b7c7d13d4df6c5bf3f9` is its second parent after `944269a771c6f6300d6f8a559866ade9e262a56b`. Candidate checks, exact-main QG, CI, Docker, invariants, Docs Deploy, and Codex CI passed. Forge Smoke was skipped by its configured condition. Exact-main QG artifact #12157267933 matched GitHub's SHA-256 and records Administrator UID 0, strict audit, immutability, and 29/29 acceptance. CI artifact #12158235129 also matched its GitHub SHA-256; source validation, canonical planning, and World-State acceptance passed 11/11, 20/20, and 3/3.

Sequence 417 records the merge and exact-main verification in `work/construction/segments/0417-verify-sequence416-merge-main.md` and `work/construction/evidence/0417-verify-sequence416-merge-main.json`.

## Open evidence boundaries

- Federation Health run #39184847466 succeeded on prior main `944269a771c6f6300d6f8a559866ade9e262a56b`; the next scheduled run on `1ee81c45efcc0565ea294944707e725ffaad3b6c` is pending.
- Scheduled Nightly Audit Integrity and Nightly Self Check on current main are pending. Existing strict checks and least-privilege workflow scopes remain intact.
- Historical test provenance remains `INTEGRITY_BROKEN` at an unanchored start, including the preserved sequence-286 loss. No historical evidence was reconstructed.
- No production resident A→B→A trial or production inference occurred. Commissioned A/B identities, distinct serving approvals, and operator preregistration remain required.
- Sequences 382–386 and every earlier segment/evidence record remain in the append-only construction index. The stale sequence-178 workspace remains untouched.

The immutable atlas remains bound to its historical source. CI and synthetic rehearsal evidence do not establish production learning or improvement. No workflow or runtime authority changed.

Latest verified main: `1ee81c45efcc0565ea294944707e725ffaad3b6c`, tree `d2ae2319b22a1c38fbe25178d525436e1c21dde3`.
Latest construction segment: `work/construction/segments/0417-verify-sequence416-merge-main.md`
Latest segment SHA-256: `2c1f35838367dcceac17262548d98eddbc55548d479a64bee8f8474ea20a39a6`
Sequence: 417 (regular merge and exact-main post-merge checks verified)
