# Sequence 503 — authenticate delegated stage-approval issuers

PR #2506 makes stage approval fail closed unless its canonical artifact is explicitly approved, correctly typed, digest-valid, and bound to the current transition. Denied, pending, missing-status, malformed synthetic-policy, and issuer/signer mismatch cases receive negative regression coverage before state mutation. The authenticated operator identity comes from the Ed25519-signed request and is compared to the approval issuer.

The delegation model is explicit: membership in the pinned transition-operator trust catalog grants the narrow stage-order approval role. This role does not authorize activation, serving, inference, or writeback. The code does not claim two-person approval; a separate approver is not required under this delegated contract.

The issuer field changed the canonical payload. PR #2507 therefore versions the stage-approval schema to v2 and updates the fixture, preventing a v1 approval from being silently interpreted under the new payload shape.

PR #2506 candidate `c79634a0ad060367c8dea57717bf10570845b4e0` merged as `e416730084c4b9f35b160e0a889c311bbdc59a90`. Schema correction candidate `991842bbe152e6567252e682f8de1c0dab6c029f` merged as `385f425ad118e15dde85eb5b6b2c39cdabb9b401`, preserving commit history. The final merge is signed, has ordered parents `e416730084c4b9f35b160e0a889c311bbdc59a90` and `991842bbe152e6567252e682f8de1c0dab6c029f`, and its tree `16366dc901b19f19796af53db828a67eeec159c8` matches the candidate tree. The remote `main` ref independently resolves to this merge.

Five focused local suites passed (174 tests), and targeted compilation, diff checks, and the Mypy baseline ratchet passed with zero new errors. Local provenance is supplemental and is not presented as candidate-SHA-bound. On the exact candidate, hosted CI and the Quality Gate passed, including the integrated resource-to-cognition and receipt/planning checks, exact-candidate acceptance, actual Administrator strict audits, immutability verification, and the separate pre-publication metadata guard. Post-merge CI, Quality Gate, Codex CI, Release, Docker, CPU smoke, invariants, docs deployment, and Helm checks passed; Forge Smoke was skipped by its workflow condition.

No production model transition or inference was run. Current-head scheduled health/audit evidence is not claimed. Federation Health report generation remains separate from unattended publication, which still requires an administrator-authorized Actions setting change or a separately provisioned least-privilege GitHub App credential.

Next, continue testing delegated approval binding and denial at the experiment boundary with synthetic inputs only, while preserving the no-activation/no-inference boundary. Keep the Federation Health publisher configuration issue visible as an infrastructure dependency.

Latest verified source merge: `385f425ad118e15dde85eb5b6b2c39cdabb9b401`, tree `16366dc901b19f19796af53db828a67eeec159c8`
Latest construction segment: work/construction/segments/0503-authenticate-delegated-stage-approval-issuers.md
Sequence: 503
