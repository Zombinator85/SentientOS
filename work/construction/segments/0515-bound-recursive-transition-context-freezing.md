# Sequence 515 — bound recursive transition context freezing

The immutable approval snapshot now rejects cyclic object graphs and nesting deeper than 64 container levels with explicit transition-domain errors. This prevents malformed direct-constructor inputs from ending in an uncontrolled Python recursion failure and places a clear resource bound on the recursive freeze. Mapping entries are snapshotted once before key validation and freezing, so the keys and values checked are the same collection view. Regression coverage includes a self-referential mapping and a 100-level nested list.

Sequence 514 merged via PR #2521 as `b480dff1219e53ea0280b44b82c53053c92c0b42`, tree `6215482f905b5dc888b2dfddf41810f6ac9eab6f`, preserving the ordered parents `c10db1dd8bf68a440b4672744a12d3d89d96a18d` and `51704a65e0415577f8161652e55a3f4edd0c7aca`. Its exact-candidate Required Quality Gate, actual Administrator strict audits, hosted finalizer, separate metadata guard, CI, docs, self-check, Helm, Docker, Release validation, Codex CI, invariants, and Gradient checks passed. Post-merge main Quality Gate, CI, docs, self-check, Helm, Docker, Docs Deploy, CPU smoke, and invariants passed; Forge Smoke was conditionally skipped.

Supplemental local verification passed 92 affected tests with 0 failures and 0 skips. Targeted Mypy, compileall, workflow YAML parsing, diff checks, and custody over 514 predecessors passed. Exact-candidate hosted verification for sequence 515 is pending. No production transition, activation, serving, inference, or writeback was performed.

Verified main base: `b480dff1219e53ea0280b44b82c53053c92c0b42`, tree `6215482f905b5dc888b2dfddf41810f6ac9eab6f`
Implementation candidate: `534050c1572280ed65d0a13f3663a9cca770880f`, tree `0202678592db9e1bb2b18f4f2a1ab5bec5e1f7ee`
Sequence: 515 (candidate pending hosted verification)
