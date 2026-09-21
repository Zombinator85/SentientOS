# Causal Resource Principal Architecture

> **Posture — root identity evidence plus one bounded producer/consumer composition implemented; wider architecture remains non-runtime and non-authority.** `sentientos/causal_resource_principal.py` implements inert root evidence, and `sentientos/genesis_forge.py` may explicitly carry a caller-supplied existing root to `sentientos/control_plane_kernel.py`, which projects canonical evidence into descriptive proof-budget context. Neither surface implements allocation, child propagation, consumption, enforcement, entitlement, or effect authority. Possessing or observing a principal confers nothing and allocates nothing.

**Inspected revision:** `168fde46163676cb913887282088a3687d7d7bf4`  
**Inspection time:** `2026-09-21T07:28:58Z`  
**Initial repository state:** clean `work` branch at the inspected merge revision; the checkout exposed no local `main` ref or remote, so that exact clean HEAD is the available fresh-current main snapshot. The repository bootstrapper returned `ready` before edits.

## 1. Executive decision

SentientOS now has the bounded root-evidence slice of a **new, thin causal resource principal**. It identifies one sponsored causal activity and its lineage; it contains no CPU, RAM, GPU, token, retry, deadline, priority, quota, capability, grant, or admission. Independent resource-specific allocators may bind allocations and consumption receipts to it. In short: **unify causal identity; do not unify resource semantics**.

No current identity is sufficient. In particular, `work_item_id` is a useful correlation binding, not a trust root: intake is explicitly metadata-only, its ID is a 16-hex truncation of four caller-influenced metadata fields, and it carries neither issuer evidence, lineage, epoch/currentness nor allocator custody. Reusing effect admission would collapse authority into accounting; reusing a correlation ID would trust caller data. The deliberate choice is therefore option C: mint a separate deterministic principal and bind the external work item where present.

The service rule is adopted: **work performed on behalf of a caller retains that verified causal attribution unless an explicit independent-sponsorship transition occurs**. The authority rule is equally strict: resource availability can block, defer, narrow, safely degrade, or terminate work; it can never broaden effect authority.

## 1.1 Runtime implementation status

**Implemented now:** canonical `sentientos.causal_resource_principal:v1` immutable root evidence, an injected operator-sponsorship verification boundary, deterministic issuer-derived identity and binding, strict mapping, deterministic explicit-time verification, and bounded observation-only causal attribution at the explicit proof-budget control-plane boundary. Roots have no parent and use an all-zero SHA-256 genesis predecessor.

**Still not implemented:** resource allocations, allocation ledgers, child principals, delegation, causal propagation, async custody, consumption receipts, retries/accounting integration, resource enforcement, admission integration, generic causal propagation, local-model budget binding, external-model quotas, provider billing, GPU accounting, host scheduling, resident composition, revocation registry, or renewal generations. `work_item_id` remains correlation only and is omitted from this smallest evidence surface.

The bounded GenesisForge composition path is now implemented: one top-level invocation may explicitly reuse the same caller-supplied root for several needs, without child derivation, minting, generic propagation, allocation, admission influence, or proof-budget influence. The next smallest justified slice is authenticated issuer provenance and custody for a real runtime root producer; canonical self-binding alone is not issuer authentication.

### Canonical verification is not issuer authentication

The control-plane projection uses the kernel-owned injected clock, rendered as canonical second-resolution UTC, and the existing `CausalResourcePrincipalVerifier`. A successful `canonical_root_binding_verified` status proves canonical root shape, identity/binding consistency, and current validity. Because the evidence is self-sealing rather than issuer-signed, it is **not** independent cryptographic proof that an untrusted serialized mapping originated from `RootPrincipalIssuer`. This bounded observation is safe only because it cannot grant, allocate, admit, or change proof-budget policy; caller `run_context` remains ordinary untrusted metadata. Invalid evidence is reduced to a closed rejection status and is never echoed.

## 2. Current-state evidence

The system atlas distinguishes implemented, composed, enabled, and exercised surfaces. Current `sentientosd` composes read-only host observation and proposal production, while local inference has separate serving and per-generation admission. External-model custody is configured/operator-invoked and unavailable by default. Runtime grant and admission ledgers govern effects, not resource entitlement.

Repository observations that constrain this design:

- `work_item_intake.py` normalizes metadata, explicitly denies execution authority, and derives estimates and a deterministic correlation identifier.
- Host resource governor/policy/runtime observe pressure under bounded collection and emit proposal-only evidence; they do not schedule, throttle, or mutate the host.
- Risk, Forge, proof-routing, maintenance, and model-invocation “budgets” have different principals, arithmetic, persistence, and composition. Their common noun is not evidence of equivalence.
- Governed local invocation bounds characters, generation tokens, calls per correlation, and timeout in a component-local invoker; caller linkage is ordinary data.
- External execution custody has exact admission/material/credential/transport bindings and hash-linked effect receipts, but no provider-spend allocation ledger.
- Runtime grant, operational feasibility, admission, execution custody, receipt, and adoption are already distinct. Resource evidence must preserve rather than shortcut that chain.

Relevant architecture evidence inspected included the current repository atlas (JSON and Markdown), public technical overview, FIDES comparative audit (JSON and Markdown), `DOCTRINE.md`, `SEMANTIC_GLOSSARY.md`, all source paths in the crosswalk below, their focused tests, and `sentientosd.py`. Source existence was not treated as composition or enforcement.

## 3. External research inputs, not repository facts

Resource Containers motivate separating a resource principal from a protection domain; Scout motivates logical path identity across components; seL4 scheduling contexts motivate on-behalf-of entitlement without transferring effect authority; structured concurrency motivates explicit child lifetime; distributed tracing motivates propagation but also shows why baggage is not trustworthy; hierarchical schedulers motivate resource-specific conservation; heterogeneous resources reject universal arithmetic; and metareasoning motivates model estimates while deterministic machinery retains allocation. These inputs survive only as design guidance and make no claim about current SentientOS implementation.

## 4. Alternatives considered

| Alternative | Decision | Reason |
|---|---|---|
| `component_budgets_only` | **reject** | preserves local limits but cannot attribute causal work across services or durable queues |
| `monolithic_task_resource_envelope` | **reject** | collapses nonfungible, temporal, capacity, rate, environmental, and consumable laws into unsafe universal arithmetic |
| `thin_principal_resource_specific_ledgers` | **adopt** | adds shared causal identity without turning identity into entitlement or effect authority |
| `extend_work_item_id` | **reject** | work_item_id is truncated metadata-derived correlation, caller-influenceable, has no issuer proof, epoch, lineage, currentness, or allocator binding |
| `reuse_admission_or_correlation_identity` | **reject** | admission is effect authority and correlation IDs are caller data; reuse would collapse boundaries |

Component budgets remain valuable enforcement mechanisms, but cannot alone supply cross-service causal attribution. A monolithic envelope is rejected because addition, refund, replenishment, occupancy, exclusivity, safety and time are not one law. Extending an existing identity is rejected because current identities have deliberately narrower trust meanings.

## 5. Chosen minimal primitive and records

A future `CausalResourcePrincipal` is immutable evidence with: `principal_id`, root and optional parent IDs, sponsor-evidence and subject-binding digests, issuer, epoch/generation, issue/expiry time, predecessor-generation digest, and canonical binding digest. Optional work-item, admission, invocation, or maintenance references are digest-bound correlations, never inherited authority.

Only three conceptual record families are necessary:

### CausalResourcePrincipal

**Purpose:** immutable causal identity and lineage anchor. **Owner/issuer:** resource-principal issuer. **Required content:** principal_identity.required_fields. **Lifecycle:** issued, current, expired/revoked/superseded. **Staleness/replay:** epoch, expiry, predecessor digest, issuer currentness and revocation lookup. **Mutation:** immutable; change creates a new generation. **Durability:** required across process/persistence boundaries; optional for purely synchronous process-local work until boundary. **Authority:** neither effect authority nor entitlement. **Relationship:** binds evidence digests without replacing their verification.

### ResourceAllocation

**Purpose:** resource-specific entitlement or reservation. **Owner/issuer:** resource-class allocator. **Required content:** ['allocation_id', 'principal_binding_digest', 'resource_kind', 'resource_specific_bounds', 'validity', 'allocator_id', 'epoch', 'policy_digest', 'allocation_digest']. **Lifecycle:** issued, optionally reserved/delegated, consumed/reconciled, released/expired/revoked. **Staleness/replay:** allocator sequence/epoch, validity and current principal generation. **Mutation:** append state transitions or replacement record; never edit issued evidence. **Durability:** resource-specific; mandatory before irreversible/external spend. **Authority:** resource entitlement only; never effect authority. **Relationship:** independently checked beside any effect admission.

### ResourceConsumptionReceipt

**Purpose:** record attempted/measured use and reconciliation. **Owner/issuer:** trusted resource gate/meter. **Required content:** ['receipt_id', 'allocation_digest', 'principal_binding_digest', 'attempt_id', 'resource_specific_measurement', 'state', 'observed_at', 'previous_receipt_digest', 'receipt_digest']. **Lifecycle:** attempted, measured, reconciled; corrective records append. **Staleness/replay:** unique attempt id, sequence/hash link, allocation epoch. **Mutation:** append-only. **Durability:** mandatory where crash/retry could double spend or external cost is irreversible; otherwise resource policy decides. **Authority:** evidence only. **Relationship:** separate from effect receipt; cross-links attempt/effect receipt when both exist.

Delegation is intentionally a resource-specific transition within `ResourceAllocation`, not a fourth universal record. A delegation binds parent allocation, child principal, exact transfer rule, and remaining entitlement. It cannot mint capacity or translate between resource kinds.

## 6. Identity lifecycle

- **Child Creation:** Issuer derives a child for a separately cancellable/observable semantic sub-action, binding parent current generation and a resource-specific delegation if entitlement is transferred.
- **Durability:** Seal before queue/process/restart boundaries.
- **Generation:** Required to make renewal/revocation/currentness explicit; generation does not replenish allocations.
- **Revocation Expiry:** Verifier rejects expired, revoked, superseded, broken-predecessor, or non-current issuer epochs. Cancellation normally cascades to descendants subject to safe resource cleanup.
- **Root Creation:** Only a deterministic issuer may mint after validating explicit sponsor evidence (operator task, adopted maintenance configuration, or other future registered sponsor); bind work_item_id only as correlation.
- **Same Principal Rule:** Propagate the same principal for ordinary service calls, implementation details, batching participation, and retries on behalf of the same activity.

Renewal produces a new generation; it does not reset consumption. Identity mutation is forbidden. Pure synchronous calls can carry trusted in-process context, but persistence, process, queue, or restart boundaries require sealed durable evidence or a trusted-store reference.

## 7. Root, child, and shared lineage

- **Child Budget:** Child creation creates no entitlement. Delegation cannot exceed/resource-incompatibly transform the parent allocation.
- **Child Outlives Parent:** No by default. Only a pre-expiry independent-sponsorship transition creates a new root; historical attribution cross-links the old child without inheriting entitlement.
- **Detached Work:** Cannot remain an escaping child. It either remains cancellation/revocation-bound to its parent or completes an explicit independent-sponsorship transition before detach.
- **Independent Sponsorship:** A fresh root issued from separately verified sponsor evidence with its own lifecycle and allocator decisions; relabeling, detaching, queueing, or choosing a new ID is insufficient.
- **Parent End:** Cancel/revoke/expire child eligibility and resource-specific allocations unless an allocator recorded a valid narrower survival rule; effect cleanup remains separately authorized.
- **Shape:** tree_for_sponsorship; shared work records a participant set/DAG reference outside parentage
- **Shared Work:** Do not create multiple parents. Record participant causal references and let the resource subsystem allocate cost.

A root is created only after a deterministic issuer validates explicit sponsor evidence—for example an operator task or adopted maintenance configuration. Independent sponsorship means fresh verified sponsor evidence, its own lifecycle, and new allocator decisions. Detachment, a new UUID, a queue message, urgency, or a service boundary is not sponsorship. A meaningful, separately cancellable sub-action may receive a child; ordinary helper calls, retries, and implementation details retain the same principal.

Sponsorship lineage remains a tree. Shared cache, index, validation, or batch work may have multiple causal participants, so participant attribution is a separate DAG-like relation; pretending it has multiple parents would corrupt cancellation and entitlement semantics.

## 8. Propagation semantics

| Surface | Rule |
|---|---|
| direct function/service invocation | propagate the same verified principal binding by trusted in-process context; derive child only for meaningful independent lifecycle |
| local model invocation | bind verified principal to a future allocation adapter; keep local inference admission independent; caller_linkage/correlation_id are not proof |
| external model invocation | durably bind principal/allocation/attempt before transport; final pre-effect check requires current effect admission and current allocation |
| asynchronous tasks and queues | enqueue sealed principal evidence or a trusted reference plus issuer/epoch/currentness proof; arbitrary task metadata is insufficient |
| retries | reuse causal principal and stable logical operation identity; each attempt is unique and prior consumption remains visible |
| maintenance work | mint independently sponsored root from adopted operator configuration/run evidence, not from ambient resident status |
| future sub-agents | same principal for implementation detail; child for separately cancellable subtask; allocation requires delegation |
| durable/replayed work | reverify binding, sponsor, generation, expiry, revocation, allocation and attempt history before work |
| independent sponsorship transition | explicit issuer-mediated child-to-new-root transition bound to fresh sponsor evidence; never inferred from detachment |

Plain dictionaries, tracing baggage, prompt text, model output, `correlation_id`, and `work_item_id` are never sufficient evidence. At a durable boundary the consumer verifies canonical digest, issuer, sponsor, generation/predecessor, expiry, revocation and—where spend is requested—the independent allocation and attempt history.

## 9. Resource-class taxonomy

There is deliberately no generic `amount` or universal conservation boolean. Shared mechanics are only binding, currentness, issuer verification, resource-kind dispatch, attempt identity, and auditable transitions. Arithmetic and lifecycle belong to each resource class.

| Class / examples | Conservation | Replenishment / return / reclaim | Reservation & measurement | Exhaustion | Current feasibility |
|---|---|---|---|---|---|
| **consumable**<br>provider calls, provider spend, search/tool calls, retries, proof attempts, token quota | strict_for_delegated_units | none; unused units may be returned before expiry; spent units never reset; unspent units may be reclaimed | optional preauthorization/hold; exact for calls/retries; provider money/tokens depend on trusted receipts | deny, narrow, or stop; never expand authority | partial: local calls/proof attempts bounded; no unified ledger |
| **replenishing_rate**<br>CPU budget per period, request rate, bandwidth | window_scoped_conservation | periodic_window; not a refund; later windows replenish; future-window capacity may be reclaimed | token bucket/window reservation is resource-specific; rate/count exact when trusted gate owns attempts; CPU/bandwidth approximate | delay, queue, shed, or stop | partial: bounded loops/timeouts exist; no causal rate ledger |
| **capacity**<br>RAM, VRAM, disk occupancy | concurrent_capacity_not_spend_conservation | capacity changes with occupancy; release frees capacity; leases/allocations reclaimable subject to safe teardown | yes, occupancy lease; RAM/VRAM/disk attributable measurement is approximate or unavailable | block, evict only by explicit safe policy, or degrade | observation feasible; causal enforcement absent |
| **reservation**<br>CPU share, accelerator slice, model slot | exclusive_or_share_specific | none unless periodic share; release returns the reserved share; lease expiry/revocation where safe | defining semantic; reservation state exact; physical consumption may not be | wait, reject, or release | not currently implemented as causal allocation |
| **temporal**<br>deadline, maximum wall clock, expiry | deadline_monotonic_narrowing | wall-clock progression; no; elapsed time cannot be returned; future time window may be cancelled | deadline/lease expiry rather than quantity reservation; timestamps exact within clock assumptions; work causality not automatic | cancel, time out, or decline retry | timeouts exist component-locally |
| **nonfungible**<br>exclusive accelerator, device, future actuator reservation | identity_and_exclusivity | none; release returns the same item, not fungible value; lease-based when safe | exclusive lease required; ownership/lease state exact; utilization separate | queue or reject; never substitute an actuator implicitly | not implemented for causal principals |
| **environmental**<br>thermal headroom, energy, battery, power | safety_policy_not_parent_sum | physical/environmental recovery; not caller-refundable; system may reclaim all headroom | safety reserve only; never promised as durable spend; observed/estimated, not exactly attributable | throttle, defer, degrade, or stop safely | read-only host telemetry; no actuation |
| **logical_epistemic**<br>verification passes, model escalation allowance, research depth | strict_counts_when_discrete_otherwise_policy_bounded | policy-specific; unused discrete attempts may return; completed verification cannot; unstarted allowance reclaimable | optional; attempt counts exact; research depth/utility are proxies | stop, require review, or return insufficient evidence; never skip mandatory verification | proof budget governor exists; no causal binding |

Strict parent/child conservation is sensible only for discrete delegated consumables and some explicitly quantified shares/reservations. Rate windows conserve within a defined window. Capacity is concurrent occupancy, time only narrows, environmental headroom is a safety observation, and nonfungible identity cannot be summed. Borrowing is denied by default and may be introduced only by a versioned resource-specific policy that protects system reserves. Unused entitlement can be returned only where the row permits; completed consumption never becomes unused through retry or generation rollover.

## 10. Allocation, delegation, reservation, and consumption

The principal answers **whose causal activity?** An allocator-owned allocation answers **what bounded resource, under which resource law, may be used?** A reservation holds capacity; it is not consumption. A consumption receipt reports attempted/measured/reconciled use and carries evidence, not permission. Allocation issuance is separate from enforcement: only a trusted resource gate can enforce, meter, and reconcile.

Required state vocabulary is resource-selective: allocation issued; reservation made; consumption attempted; consumption measured; effect attempted; effect outcome known; resource reconciliation complete; allocation released, expired, or revoked. Not every resource needs every state, but no subsystem may collapse states it needs for crash or retry safety.

## 11. Authority relationship and non-collapse analysis

Effectful execution may require two independently current statements: (1) effect authority says this exact effect may occur, and (2) resource allocation says this bounded work may be spent performing it. Neither manufactures the other. Principal possession grants no filesystem, network, provider, host, model, maintenance, adoption, repository, credential, grant-issuance, admission-issuance, or resource-expansion authority.

- `state != authority` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `memory != current truth` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `proposal != authorization` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `authorization != execution` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `execution != validation` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `validation != adoption` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `capability definition != grant` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `grant != operational feasibility` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `operational feasibility != admission` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `admission != execution` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource identity != effect authority` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `authority != resource entitlement` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource entitlement != resource consumption` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource need estimate != resource allocation` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource allocation != enforcement` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `reservation != consumption` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `priority != authority` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `urgency != authority` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `criticality != authority` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `deadline != authority` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource scarcity != authorization failure` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `budget delegation != budget creation` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `child creation != entitlement creation` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource exhaustion != authority escalation` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `unused allocation != permission` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.
- `resource receipt != effect receipt` — maintained by distinct issuer, record type, verifier, lifecycle and/or final gate; no record is accepted as a substitute for the record on the other side.

In particular: priority, urgency, criticality and deadlines are allocator inputs, never authority; scarcity is a resource outcome, not authorization failure; child creation is lineage only; delegation transfers an existing resource-specific bound and creates none; exhaustion cannot escalate privilege; unused allocation permits no effect; and resource receipts are cross-linked to but distinct from effect receipts.

## 12. Operational feasibility and admission

Do not add allocation logic casually to `runtime_admission.py`. Resource-class checks may occur early to narrow planning. For an effect path, grant, operational feasibility, and effect admission remain independently verified; a final current allocation check occurs **after effect admission and immediately before the effect attempt**, with in-flight metering where relevant. Resource evidence can only make feasibility narrower or block/delay it. Non-effectful computation may require allocation without any effect admission.

## 13. Async, durable, crash, and retry semantics

Before an irreversible external/provider attempt, persist the allocation/reservation binding and stable logical-operation plus unique attempt ID. If the process crashes after the attempt but before a resource receipt, the attempt is indeterminate: conservatively charge or hold it until resource-specific reconciliation; refund only from trusted contrary evidence. If a process crashes after a reservation but before use, an expiring lease permits reclamation only after expiry and a safe-use check.

Retries retain the same principal and logical operation, receive unique attempt IDs, and preserve all prior attempted/measured consumption. A new attempt cannot reset history. Effect-specific idempotency keys should be used where available. The architecture promises no generic exactly-once execution, measurement, or receipt semantics.

## 14. Shared work, caches, and batching

Causal attribution and economic allocation are different. The principal mechanism records participating principal bindings for shared caches, preloaded models, common artifacts, indexes, batch inference, and validation. Each resource-specific subsystem owns a versioned cost-sharing policy; no universal first-pays, equal-split, or Shapley rule is selected. Current SentientOS does not establish precise per-task physical GPU accounting. Tokens, calls, wall time, or batch shares are possible future proxies, not current facts.

## 15. Model role

Stochastic cognition may estimate usefulness, cost, and uncertainty, and propose an allocation or decomposition. Deterministic resource machinery owns capacity, policy evaluation, constraint checks, allocation, delegation, revocation, enforcement, accounting, and reconciliation. Model statements such as “urgent,” “unlimited tokens,” “skip verification,” or “give this child more GPU” carry no resource authority. A model-produced request is a proposal and cannot mint an allocation.

## 16. Threat model

| Threat | Architectural invariant / future enforcement point |
|---|---|
| caller-forged resource identities | verify issuer seal and canonical binding; IDs alone have no meaning |
| caller-forged allocation records | accept only allocator-owned sealed/current records |
| child budget inflation | resource-specific delegation conserves or narrows parent bounds |
| low-budget work laundering through a high-budget service | service work retains caller attribution unless explicit sponsorship |
| detached async work escaping lineage | detach requires issuer-mediated independent sponsorship |
| stale allocation epochs | verify principal and allocation generations/currentness |
| replayed allocation evidence | unique allocation/attempt IDs plus sequence/hash/revocation checks |
| retries exceeding quota | retain logical-operation attempt history across retries |
| resource exhaustion bypassing verification | mandatory verification cannot be waived by scarcity |
| resource exhaustion causing unsafe fallbacks | fail closed or use separately authorized safe degradation only |
| recursive subtask explosion | bound child count/depth and require delegation/allocation |
| priority inflation | priority is allocator policy data and never authority |
| shared-cache abuse | cache access and charging use explicit resource policy with participant attribution |
| batch-accounting ambiguity | record participants and use explicit proxy/policy; make no precision claim |
| safety/maintenance reserve starvation | allocators reserve protected capacity outside caller delegations |
| resource metadata accidentally becoming effect authority | all effect gates verify independent authority; metadata never satisfies grant/admission |

## 17. Current SentientOS budget crosswalk

This table refuses equivalence-by-name. “Current status” distinguishes observation, proposal, policy, enforcement, and effect custody; “composition” states what is actually wired.

### host resource observation/governor/policy/runtime

- **Source Paths:** `sentientos/host_resource_governor.py`, `sentientos/host_resource_policy.py`, `sentientos/host_resource_runtime.py`, `sentientosd.py`
- **Test Paths:** `tests/test_host_resource_governor.py`, `tests/test_host_resource_policy.py`, `tests/test_host_resource_runtime.py`
- **Current Principal:** correlation-scoped observation epoch, not resource principal
- **Resource Bounded:** collector concurrency and deadlines; observed host pressure
- **Current Status:** live resident read-only observation plus proposal-only policy
- **Allocation Owner:** static runtime plan
- **Consumption Measurement:** collector calls/timeouts and telemetry, not task consumption
- **Durable State:** evidence bundles may persist
- **Parent Child Semantics:** none
- **Cross Service Propagation:** correlation id deduplicates one coordinator process only
- **Receipt Evidence:** observation/proposal receipts explicitly non-authority
- **Current Runtime Composition:** resident composed in sentientosd
- **Proposed Relationship:** future environmental/capacity observer; not allocator
- **Recommendation:** adapt

### risk budget

- **Source Paths:** `sentientos/risk_budget.py`
- **Test Paths:** `tests/test_autonomy_budgets.py`
- **Current Principal:** repository/runtime posture
- **Resource Bounded:** router and Forge policy ceilings
- **Current Status:** component policy, persisted snapshot
- **Allocation Owner:** deterministic posture derivation plus guarded environment override
- **Consumption Measurement:** not per-task consumption
- **Durable State:** glow JSON and pulse JSONL
- **Parent Child Semantics:** none
- **Cross Service Propagation:** downstream values copied, not causal context
- **Receipt Evidence:** risk-budget snapshot/event
- **Current Runtime Composition:** used by Forge/autonomy surfaces, not universal runtime allocation
- **Proposed Relationship:** remain policy input; do not reinterpret as entitlement
- **Recommendation:** keep_separate

### Forge budget

- **Source Paths:** `sentientos/forge_budget.py`
- **Test Paths:** `tests/test_autonomy_budgets.py`
- **Current Principal:** one Forge reclamation run
- **Resource Bounded:** iterations, fixes, files
- **Current Status:** component-local configured enforcement
- **Allocation Owner:** environment-derived config
- **Consumption Measurement:** loop counters
- **Durable State:** process-local
- **Parent Child Semantics:** none
- **Cross Service Propagation:** none
- **Receipt Evidence:** none
- **Current Runtime Composition:** callable component
- **Proposed Relationship:** possible later consumable counters keyed by principal
- **Recommendation:** adapt

### proof budget governor

- **Source Paths:** `codex/proof_budget_governor.py`
- **Test Paths:** `tests/test_proof_budget_governor.py`
- **Current Principal:** routing/governor pressure state
- **Resource Bounded:** K/M proof-routing bounds
- **Current Status:** deterministic component enforcement with durable pressure state
- **Allocation Owner:** governor configuration
- **Consumption Measurement:** route decisions and pressure metrics
- **Durable State:** atomic hash-linked pressure state and recovery files
- **Parent Child Semantics:** none
- **Cross Service Propagation:** none; one explicit control-plane input can carry canonical root evidence
- **Receipt Evidence:** budget decisions, pressure state, and optional bounded descriptive attribution
- **Current Runtime Composition:** Codex routing flow plus observation-only control-plane projection, not a resident universal allocator
- **Proposed Relationship:** arithmetic remains component-local and principal-independent; control-plane evidence may observe a canonically verified root identity
- **Recommendation:** adapt

### maintenance scheduler bounds

- **Source Paths:** `sentientos/maintenance_loop_scheduler.py`
- **Test Paths:** `tests/test_maintenance_loop_scheduler.py`
- **Current Principal:** adopted scheduler configuration/run sequence
- **Resource Bounded:** cadence, run count, wall-clock duration
- **Current Status:** configured bounded scheduling
- **Allocation Owner:** operator-adopted configuration
- **Consumption Measurement:** events, attempts, elapsed time
- **Durable State:** external append-only event ledger with sequence/hash
- **Parent Child Semantics:** no child budget
- **Cross Service Propagation:** passes explicit run metadata only
- **Receipt Evidence:** scheduler events and receipts
- **Current Runtime Composition:** configuration-selected maintenance owner
- **Proposed Relationship:** maintenance roots require independent operator sponsorship
- **Recommendation:** keep_separate

### work-item estimates

- **Source Paths:** `sentientos/work_item_intake.py`
- **Test Paths:** `tests/test_work_item_intake.py`
- **Current Principal:** deterministic work_item_id over limited metadata
- **Resource Bounded:** estimated files, lines, implementation and validation seconds
- **Current Status:** metadata-only estimate/proposal
- **Allocation Owner:** caller payload normalized by intake
- **Consumption Measurement:** none
- **Durable State:** packet only when caller persists it
- **Parent Child Semantics:** none
- **Cross Service Propagation:** none
- **Receipt Evidence:** normalized packet/decision
- **Current Runtime Composition:** intake adapter, not trusted resource machinery
- **Proposed Relationship:** bind a separately minted root to work_item_id; never reuse it as entitlement
- **Recommendation:** keep_separate

### governed local-model invocation budget

- **Source Paths:** `sentientos/governed_local_model_invocation.py`, `sentientos/local_model_serving_inference.py`
- **Test Paths:** `tests/test_governed_local_model_invocation.py`, `tests/test_local_model_serving_inference.py`
- **Current Principal:** correlation id/request plus active serving lifetime
- **Resource Bounded:** input/output chars, new tokens, calls per correlation, timeout
- **Current Status:** per-invoker deterministic checks and execution receipt
- **Allocation Owner:** request defaults plus model authority ceilings
- **Consumption Measurement:** process-local call count, output size, timeout, latency
- **Durable State:** request/decision/receipt JSON for governed invoker
- **Parent Child Semantics:** none
- **Cross Service Propagation:** caller linkage is data, not entitlement proof
- **Receipt Evidence:** local invocation receipt
- **Current Runtime Composition:** service-composed local inference path
- **Proposed Relationship:** plausible first allocation adapter; preserve independent inference admission
- **Recommendation:** adapt

### external-model custody/configuration limits

- **Source Paths:** `sentientos/external_model_operational_feasibility.py`, `sentientos/external_model_execution_custody.py`, `sentientos/external_model_material.py`
- **Test Paths:** `tests/test_external_model_operational_feasibility.py`, `tests/test_external_model_execution_custody.py`, `tests/test_external_model_material.py`
- **Current Principal:** exact invocation principal/request/custody binding, not task resource principal
- **Resource Bounded:** configuration/material/feasibility limits; no provider-spend ledger
- **Current Status:** operator-invoked effect custody, unavailable by default
- **Allocation Owner:** definition/grant/feasibility/admission chain
- **Consumption Measurement:** attempt/success response evidence, not billing
- **Durable State:** atomic hash-linked invocation receipt store
- **Parent Child Semantics:** none
- **Cross Service Propagation:** exact evidence bindings within custody chain
- **Receipt Evidence:** effect invocation receipts
- **Current Runtime Composition:** not resident-composed; configured external path
- **Proposed Relationship:** later require independent provider allocation immediately before attempt
- **Recommendation:** keep_separate

### runtime grants and admission

- **Source Paths:** `sentientos/runtime_grant_policy.py`, `sentientos/runtime_admission.py`
- **Test Paths:** `tests/test_runtime_grant_policy.py`, `tests/test_runtime_admission.py`
- **Current Principal:** operator grant/admission subject and capability
- **Resource Bounded:** effect scope and validity, not resources
- **Current Status:** effect-authority policy and ledger
- **Allocation Owner:** operator grant and admission authorities
- **Consumption Measurement:** authority decisions, not resource use
- **Durable State:** grant/admission ledgers
- **Parent Child Semantics:** revocation/expiry, not resource lineage
- **Cross Service Propagation:** exact authority evidence only
- **Receipt Evidence:** sealed grant/admission evidence
- **Current Runtime Composition:** control-plane/effect paths
- **Proposed Relationship:** orthogonal input; must never mint allocations
- **Recommendation:** keep_separate

### component retries/timeouts

- **Source Paths:** `sentientos/maintenance_loop_scheduler.py`, `sentientos/governed_local_model_invocation.py`, `sentientos/host_resource_runtime.py`
- **Test Paths:** `tests/test_maintenance_loop_scheduler.py`, `tests/test_governed_local_model_invocation.py`, `tests/test_host_resource_runtime.py`
- **Current Principal:** component-specific run/correlation/epoch
- **Resource Bounded:** attempt counts and elapsed time
- **Current Status:** locally enforced, no shared causal accounting
- **Allocation Owner:** each component configuration
- **Consumption Measurement:** component-local attempts/timeouts
- **Durable State:** mixed process-local and durable events/receipts
- **Parent Child Semantics:** none
- **Cross Service Propagation:** none
- **Receipt Evidence:** component-specific
- **Current Runtime Composition:** multiple bounded current paths
- **Proposed Relationship:** future attempt identity must retain prior consumption across retries
- **Recommendation:** adapt

## 18. Candidate implementation boundaries

Observation-only proof-budget attribution is implemented at the explicit control-plane boundary, and GenesisForge now has one bounded explicit producer path that supplies an already-existing caller root for an invocation. A governed local-model budget adapter remains later work. They must preserve their existing arithmetic and admissions. Risk, Forge, host observation/proposal, maintenance cadence, effect grants/admissions, and external custody/receipts remain intentionally separate.

The **smallest next runtime slice** is: design authenticated issuer provenance and custody for a real runtime root producer. Canonical self-binding is not issuer authentication, so this prerequisite should be closed before any resource allocation slice.

## 19. Unresolved questions

- issuer key/custody and revocation store selection.
- which roots require durable persistence before first work.
- resource-specific borrowing policies.
- shared cache and batch cost policies.
- clock trust for temporal allocations.
- safe cancellation semantics per resource.

These are bounded implementation decisions, not reasons to reopen the architectural choice.

## 20. Explicit non-goals

- No runtime principal class.
- No resource ledger.
- No resource enforcement.
- No admission changes.
- No capability or grant changes.
- No provider/network changes.
- No credential changes.
- No local inference changes.
- No host scheduling or cgroups.
- No GPU scheduler.
- No proof/risk/Forge semantic changes.
- No maintenance cadence changes.
- No background loops.
- No resident composition changes.
- No universal cost-sharing or exactly-once guarantee.

## 21. Concrete acceptance decisions

| Question | Decision |
|---|---|
| 1. `first_class_principal` | yes: a new thin first-class causal resource principal |
| 2. `existing_identity` | no; work_item_id remains external correlation and admissions/correlation IDs retain their own semantics |
| 3. `minimum_content` | immutable ID, root/parent lineage, sponsor and subject bindings, issuer, epoch/generation, validity, predecessor and binding digest |
| 4. `quota_location` | only resource-specific allocator records contain bounds |
| 5. `root_creation` | deterministic issuer after verified explicit sponsor evidence |
| 6. `child_creation` | issuer derives a bound child; entitlement requires separate resource-specific delegation |
| 7. `same_principal` | ordinary on-behalf-of calls, retries and implementation details |
| 8. `independent_sponsorship` | fresh verified sponsor evidence and issuer-mediated new root transition |
| 9. `async_lineage` | sealed durable context/reference plus revalidation |
| 10. `stale_detection` | issuer/epoch, expiry, revocation, predecessor and allocation sequence checks |
| 11. `separate_mechanisms` | risk, Forge, proof, host, maintenance, local/external custody and authority ledgers retain their laws |
| 12. `first_consumers` | observation-only proof attribution, then governed local-model budget adapter |
| 13. `strict_conservation` | discrete delegated consumables and some reservations, only under resource-specific rules |
| 14. `non_strict_conservation` | capacity, temporal, environmental, shared/nonfungible and proxy epistemic cases |
| 15. `feasibility_intersection` | early checks may only narrow/block; never create feasibility or authority |
| 16. `final_check` | after otherwise-valid effect admission and immediately before effect attempt, plus metering where required |
| 17. `receipt_relation` | cross-linked but distinct resource and effect receipts |
| 18. `deferred` | all runtime minting, ledgers, propagation, enforcement, billing, GPU accounting and cost sharing |
| 19. `next_runtime_task` | Design authenticated issuer provenance and custody for a real runtime root producer; canonical self-binding alone is not issuer authentication. |

## 22. Design contract summary

A causal resource principal is an issuer-sealed, immutable, generation-aware identity for sponsored causal work. It follows ordinary on-behalf-of work unchanged, derives children only for meaningful subordinate lifetimes, and requires a fresh verified sponsorship transition for independent/detached work. It means neither effect authority nor resource entitlement. Resource-specific allocators bind independent allocations; trusted gates meter and emit separate consumption evidence. Enforcement binds at the resource gate and, for effectful work, independently beside a valid effect chain. Root evidence is implemented; child, allocation, propagation, consumption, and enforcement mechanisms remain deferred.

## 23. Repository-grounding boundary

All “future” types and transitions above are recommendations. The crosswalk is the current-state claim surface. Nothing here updates the current-system atlas, doctrine, glossary, public overview, runtime modules, or resident composition, because doing so would falsely imply implementation.
