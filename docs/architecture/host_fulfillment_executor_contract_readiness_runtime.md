# Host Fulfillment Executor Contract Readiness Runtime

This runtime closes the executor-contract review loop without implementing an executor. It accepts exact fulfillment-authorization consumption custody, current local-grant posture, metadata-evaluation admission, and deterministic executor-contract records, then persists an external evidence bundle and projects review-only World-State/dashboard facts.

## Authority boundary

The runtime answers only whether the executor contract package is complete enough for later human/governed review. It never grants execution authority. The posture fields remain false: `execution_ready`, `executor_implemented`, `backend_loaded`, `backend_invoked`, `dry_run_executed`, `control_plane_execution_admission_granted`, `fulfillment_granted`, `privileged_effect_admission_granted`, `effect_performed`, and `host_mutation_performed`.

Backend declarations are bounded data-only metadata. Dry-run plans are declarative and unexecuted. Future-execution admission packets are request packets only; this runtime never calls control-plane execution admission.

## Canonical chain

The runtime binds the exact `HostFulfillmentAuthorizationConsumptionResult`, request envelope, source reference, successful consumption receipt, consumption ledger entry and ledger, plus current grant expiry/revocation posture. After proposal/review metadata admission allows evaluation, it composes the canonical records from `sentientos/fulfillment_executor_contract.py`: contract, backend declaration, precondition manifest, dry-run plan, admission packet, and readiness receipt.

Every downstream record carries direct parent IDs and digests. Semantic IDs exclude custody timestamps and runtime paths while including source IDs/digests, executor domain, backend class/label, scope, targets, exact current grant/verification/authorization-ledger/expiry-evaluation/revocation evidence, the derived current grant evidence posture, prerequisites, blocked actions, future gates, risk/warning codes, and no-authority assertions. Caller-supplied posture labels are diagnostic expectations only and never establish authority.

## Persistence and projection

Bundles are written atomically under an explicit external runtime-state root. Repository-local roots and symlink escapes are rejected. Persisted files include the request, source manifest, metadata admission reference, runtime plan, prerequisites, contract records, validation findings, summary, deterministic Markdown, and a compact latest pointer.

World-State projection uses proposal/review/admission-candidate lifecycle stages only. The authenticated dashboard endpoint `/api/world-state/host-fulfillment-executor-readiness` reads only terminal World-State facts and never invokes the runtime, builders, admission, backends, dry-runs, fulfillment, effects, or host mutation.

## Capability and proof

Capability: `host_fulfillment_executor_contract_readiness_runtime`.
Matrix lane: `host_fulfillment_executor_contract_readiness_runtime_tests`.
Proof artifact: `host_fulfillment_executor_contract_readiness_runtime_posture`.

## Current authority snapshot reconciliation

Executor-readiness now separates two evidence epochs. The historical epoch is the immutable fulfillment-authorization consumption custody: the consumed grant, verification, authorization ledger, expiry evaluation, revocation references, successful consumption receipt, consumption ledger entry, and consumption ledger remain recorded exactly as they existed when fulfillment authorization was consumed. The current epoch is mutable authority evidence: an exact validated `HostLocalAuthorizationLedgerSnapshot`, its underlying local authorization ledger, current grant record, current verification, current canonical expiry evaluation, ledger-contained revocation receipts, host-local issue receipt, host-local revocation receipts, validation time, and derived posture.

Historical and current verification, ledger, and expiry digests may legitimately differ. Divergence is represented as current snapshot custody, not as historical tampering, when the current snapshot preserves semantic continuity to the same historical grant ID and digest and contains the matching issue receipt and exact grant bytes. Current revocation and expiry posture are derived from the authoritative snapshot; a caller-supplied empty revocation list is never authority to omit ledger-contained revocations.

Snapshot validation recomputes nested grant, revocation, expiry, issue-receipt, host-local revocation-receipt, ledger, and snapshot digests; rejects duplicate semantic IDs with different bytes; recomputes active, revoked, expired, and conflicted counts; checks ledger/snapshot count agreement and ledger status; and verifies host-local revocation receipts cross-link to local revocation receipts. Non-positive current verification statuses (`blocked`, `expired`, `revoked`, `incomplete`, and `contradicted`) fail closed before metadata admission or executor-contract builders are called.

Replay custody is fail-closed. Persisted bundles include a deterministic bundle manifest binding every required JSON/Markdown file by artifact kind, schema version, semantic ID, digest, relative filename, and size. Exact replay validates the replay index, latest pointer, runtime receipt, request, current evidence, and bundle manifest before returning the persisted review-only result; corrupt required bundle files produce a contradicted replay instead of reusing a positive evaluation.
