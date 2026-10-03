# Production provisioning publication recovery-review contract

Schema: `sentientos.production_chat_resource_provisioning_request_recovery_review_contract:v1`

This frozen contract is deterministic, metadata-only, contract-only, and future-only. It defines an evidence standard; it does not inspect or classify an actual attempt, register or grant authority, evaluate evidence, or perform recovery. Contract metadata is not evidence, authority, or execution. The canonical machine artifact is [`architecture/production_chat_resource_provisioning_request_recovery_review_contract.json`](../../architecture/production_chat_resource_provisioning_request_recovery_review_contract.json).

## Why a doctor snapshot is not terminality

The read-only publication doctor can establish `bare_request` at one lock-free observation point. The identical custody shape can occur while a publisher is between durable request creation and receipt creation, or after that publisher has terminated. Because the doctor neither locks nor excludes concurrent publication, its report explicitly keeps `concurrent_publication_excluded == false` and `terminal_failure_inferred == false`. One report—or repeated reports—cannot select between those lifecycle histories.

**Terminal abandonment is a conjunctive evidentiary classification, never an inference from one lock-free custody snapshot.** Time passage is not terminality evidence. Lock pathname state is not publisher-attempt lifecycle evidence. PID or process-list absence is likewise insufficient.

## Exact evidence conjunction

A future review may return `terminal_abandonment_evidence_complete` only when all five classes are present, internally valid, mutually bound, and non-contradictory:

1. A doctor report bound to installation identity **I**, provisioning ID **P**, exact request-storage SHA-256 and byte size, and the request digest when valid. It must report `bare_request`, incomplete publication, a lock-free snapshot, no excluded concurrent publisher, and no inferred terminal failure. This is necessary but insufficient.
2. Immutable publisher-attempt identity evidence created before the first durable publication mutation. It binds one unique attempt ID, I, P, exact request identity, publisher authority-definition digest, principal, canonical start instant, evidence digest, and independently verifiable governed lifecycle provenance. It must never be synthesized retrospectively.
3. Immutable terminal closure from that governed boundary for the same attempt ID and bindings. It proves the exact invocation is terminal, request creation completed, receipt creation did not, no execution for the attempt remains active, and records an explicit outcome, reason, canonical terminal instant, and provenance. It distinguishes success from failure, abort, or cancellation before receipt completion.
4. A second same-request doctor observation after closure, proving the same bare request and genuine receipt absence. This guards against overlooking custody that completed after the first observation; the doctor remains lock-free and non-authoritative.
5. No contradictory evidence, including a valid completed receipt, any identity/hash/digest/attempt/authority mismatch, success, closure before request creation, completed receipt creation, or unverifiable provenance.

The publisher authority-definition digest is `349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5`. Attempt identity cannot be replaced by I/P alone.

## Current gap and denied inferences

The repository has no governed pre-effect publisher-attempt identity artifact, terminal publisher-attempt closure artifact, or independently verifiable lifecycle provenance. Therefore terminal-abandonment classification, recovery authority, and same-ID reuse authority are all currently unavailable. Repeated snapshots, timeout or file age, mtime/ctime, lock existence/absence/age, unrelated lock acquisition, PID/process/PID-file absence, restart or uptime, caller/operator/chat/model claims, unauthenticated log text, request/intent validity, burn semantics, consumer rejection, doctor incompleteness, and the retry prohibition cannot fill those gaps.

## Classification is not recovery authority

Even complete evidence means only that the evidence standard for classifying this exact attempt is satisfied. It grants no deletion, repair, cleanup, receipt completion, retry, republication, overwrite, rename/move/quarantine, provisioning-ID reuse, allocation, bundle creation, or execution. A later recovery design requires a separate governed contract and authority.

The existing request and receipt schemas and publisher, consumer, and doctor runtime behavior remain unchanged.

## Frozen pre-effect attempt-identity shape

The required `pre_effect_publisher_attempt_identity_evidence` now has a [frozen future-only contract](production_chat_resource_provisioning_request_attempt_identity_contract.md). That contract defines the missing object's exact identity, request binding, custody, and independently verifiable provenance requirements; it does not emit evidence or implement provenance verification, so `publisher_attempt_identity_evidence_missing` remains open and recovery review remains unsatisfied.
