# Sequence 338: bind transition history to resident boundary

## Increment and source identity

Before non-synthetic resident transition ingress, the daemon now requires the predecessor and successor model-replacement references to resolve to one frozen causal context. It verifies that the context's bounded selected history IDs and digests match exact records in the transition protocol's complete initial resident history boundary. Missing records, duplicate resident record identities, digest substitution, and different A/B contexts fail closed. The read-only provenance projection keeps selected history IDs/digests and their set digest separate from the complete boundary's digest/count. No authority or history access was added.

The exact candidate head was `a892d47a2f37ecab693c168dd7cbcfad561a262a`, tree `4bf7579ed07bae02c2a18ea01d0c2f6057a38fc1`, based on sequence 337 main `afe8931ff5bcdacbeda3ab5e955bd0e437da23d5`.

## Verification

The local canonical runner passed 66 focused transition composition, protocol/journal, operator, and model-replacement tests. The production lineage node covers a one-record selected subset of a two-record resident boundary, absent and substituted records, and A/B context mismatch. Compilation and whitespace checks passed. The local test provenance SHA-256 is preserved in the corresponding evidence JSON. Initial minimal bootstrap attempts were blocked by the sandbox package proxy and a protected home entry point; the declared test dependencies were then installed in a workspace-local virtual environment, where the canonical runner completed successfully.

Candidate Required Quality Gate run `39082276884` passed 29/29 exact nodes with zero failures and skips, including the lineage test. Strict Administrator verification ran at UID 0; strict audit and immutability checks passed with no issues, status `healthy_strict`. The downloaded quality-gate artifact and hosted finalizer artifacts were independently verified against GitHub's SHA-256 digests. The finalizer reported `ready_for_pr_metadata` with no reasons. Candidate CI, lint/Mypy, Docker, invariant, Release, Gradient, and Codex CI workflows passed.

## Boundary and next dependency

This binds frozen evidence identity before ingress. It does not observe running source code or establish a production A→B→A execution. The next source check should require both transition roles to reference the same preregistered model-pair protocol and validate the resident boundary's record-ID/digest summary and boundary digest against its complete records.
