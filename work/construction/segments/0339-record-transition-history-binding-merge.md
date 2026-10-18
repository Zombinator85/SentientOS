# Sequence 339: record transition history binding integration

## Increment and source identity

Sequence 338 bound the exact predecessor/successor model-replacement context to the resident transition's complete initial history boundary. Production ingress now requires the two references to use one shared frozen causal context and verifies every selected record ID/digest against the corresponding durable boundary record. Duplicate resident IDs, missing selection members, and substituted digests fail closed. The read-only lineage projection retains the selected IDs, digests, set digest, selected count, and complete-boundary digest/count separately. No history access or transition authority was added.

The exact candidate was `a892d47a2f37ecab693c168dd7cbcfad561a262a`, tree `4bf7579ed07bae02c2a18ea01d0c2f6057a38fc1`, parent `afe8931ff5bcdacbeda3ab5e955bd0e437da23d5`. PR #2328 was merged by the regular merge method. Main is `7d19f2651e8b09bd614322a1ba4ad8b2ae014218`, tree `4bf7579ed07bae02c2a18ea01d0c2f6057a38fc1`, parents `afe8931ff5bcdacbeda3ab5e955bd0e437da23d5` and `a892d47a2f37ecab693c168dd7cbcfad561a262a`.

## Verification

Local canonical regression suites passed 66/66 across transition composition, protocol/journal, operator, and model-replacement tests. The production lineage node covers the positive bounded subset, absent record, substituted digest, and mismatched-context cases. Python compilation and `git diff --check` passed. The local run provenance SHA-256 is recorded in the evidence JSON; initial package bootstrap attempts failed before collection under the blocked default proxy and protected home install path, then the declared minimal requirements were installed into a fresh workspace-local virtual environment. No protected file was changed.

Candidate Required Quality Gate run `39082276884` executed 29/29 selected tests with no failures or skips, including the transition lineage node. The independently downloaded quality-gate artifact matched its GitHub digest; it records real Administrator execution at UID 0, strict audit success, immutability success, and `healthy_strict`. The independently downloaded hosted finalizer artifact matched its GitHub digest and reported `ready_for_pr_metadata` with no reasons. Candidate CI, lint/Mypy, Docker, invariants, Release, Gradient, and Codex CI all passed.

Post-merge Required Quality Gate run `39082540831` again passed 29/29 with zero failures or skips, real Administrator verification at UID 0, clean strict and immutability audits, and `healthy_strict`. Post-merge CI, Docker, invariants, Codex CI, and Docs Deploy passed on the exact main commit. Forge Smoke was skipped by its workflow conditions.

## Production boundary and next dependency

This is verification of frozen artifact correspondence and protocol readiness, not a production A→B→A execution or observation of the running software generation. Commissioned model identities, a prepared installation, and an operator-approved protocol remain prerequisites. Sequence 338 currently allows the A and B references to name different model-replacement protocols if they share a context; the next useful source check is to require the exact same preregistered model-pair protocol for both roles and validate the resident boundary's internal record-ID/digest manifest against its records before projecting it as complete.

The changed-output Federation Health fixture remains undispatched because no workflow-dispatch action is exposed. The recorded scheduled production run was a no-op when its output matched `main`; it is not evidence of changed-output publication. Preserve sequence 286 provenance-loss evidence and leave the stale sequence-178 workspace untouched.
