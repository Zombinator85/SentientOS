# FIDES / SentientOS comparative invariant audit

> **Posture:** non-authority architecture research over SentientOS `013a0eb282715e17e19da2d2d1826ce7b07b0190`. This artifact changes no runtime or authority semantics.

## Executive finding

FIDES and SentientOS overlap in deterministic pre-effect enforcement, exact binding, non-authoritative external/model output, indirection, and audit. They differ in abstraction: FIDES is more formally crisp for content-flow integrity/confidentiality and item propagation; SentientOS is broader and more exact for authority, effect custody, provenance, freshness, generation continuity, and receipts. A global label lattice would erase useful distinctions. The clearest uncovered gap is principal-scoped **data disclosure**, not principal-scoped effect authority. Cross-domain confidentiality and derivation monotonicity are promising unifying research invariants, while cognitive quarantine is genuinely absent and should remain a targeted design question.

## Methodology and source discipline

* SentientOS evidence is the checked-out implementation and tests at `013a0eb282715e17e19da2d2d1826ce7b07b0190`; the atlas and custody report were indexes, never substitutes for source inspection.
* The audit searched modern governed custody and legacy memory/perception paths before classifying gaps.
* Public FIDES evidence was pinned to Microsoft Agent Framework commit `53e98134c91127d040daf034e889e633af4218bc`: the [Developer Guide](https://github.com/microsoft/agent-framework/blob/53e98134c91127d040daf034e889e633af4218bc/python/samples/02-agents/security/FIDES_DEVELOPER_GUIDE.md), [implementation summary](https://github.com/microsoft/agent-framework/blob/53e98134c91127d040daf034e889e633af4218bc/docs/features/FIDES_IMPLEMENTATION_SUMMARY.md), and [ADR 0024](https://github.com/microsoft/agent-framework/blob/53e98134c91127d040daf034e889e633af4218bc/docs/decisions/0024-prompt-injection-defense.md). The [Microsoft Research publication](https://www.microsoft.com/en-us/research/publication/securing-ai-agents-with-information-flow-control/) and [paper](https://arxiv.org/abs/2505.23643) anchor the research lineage.
* The available search service returned an authorization error and the guessed Learn route returned 404. Therefore a distinct current Microsoft Learn article was **not independently verified**; no behavior beyond the supplied facts and pinned Microsoft sources is inferred.
* Comparative classifications are architectural judgments, not test-proven facts or product-maturity scores.

## FIDES mechanism summary

The declared comparison set contains exactly sixteen mechanisms: integrity; confidentiality; principal-set propagation; restriction-only remote labels; tiered result labeling; conservative propagation; secure defaults for unlabeled output; sink policy; variable indirection; quarantined LLM; blind forwarding; exact approval binding; one-shot approval; session security state; audit; and the conservative-taint utility tradeoff. FIDES composes these into deterministic information-flow policy around agent/tool calls.

## SentientOS existing semantics

SentientOS models audit-chain trust, evidence strength, provenance completeness, calibration/confidence, freshness, model-output epistemic status, and authority as separate dimensions. Modern governed surfaces bind exact principals, effects, subjects, configuration digests, generation/predecessor identities, validity, and receipts. Legacy memory and perception remain materially weaker: they can retain model-authored or summarized context with uneven provenance/currentness, yet they do not thereby become effect authority. Privacy exists in perception, memory retention, credentials, prompt hygiene, external-model material custody, and bounded export/publication workflows, but it is not one cross-domain lattice.

## Mechanism-by-mechanism crosswalk

| FIDES mechanism | Security property | SentientOS analogue(s) | Exact source paths | Exact tests/proof | Semantic equivalence | Important differences | Current gap | Transferable lesson | Recommendation | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| Content integrity | Untrusted content cannot drive a sink that rejects it. | audit trust, evidence strength, provenance, freshness, calibration, external-response epistemic status, authority eligibility | `sentientos/audit_trust_runtime.py`<br>`sentientos/world_state_board.py`<br>`sentientos/external_model_material.py`<br>`sentientos/runtime_admission.py` | `tests/test_degraded_audit_trust_propagation.py`<br>`tests/test_world_state_board.py`<br>`tests/test_external_model_material.py`<br>`tests/test_runtime_admission.py` | genuinely orthogonal | SentientOS intentionally retains several axes instead of one trusted/untrusted bit. | No generic cross-domain content-integrity class or generic content-to-sink rule. | State a no-self-promotion law without flattening the existing axes. | unify_existing_invariant | high |
| Confidentiality | Public, private, and identity-scoped confidentiality constrain destinations. | perception privacy_class, memory retention/protection, credential custody, context hygiene, external-model material custody | `sentientos/perception_api.py`<br>`sentientos/canonical_memory.py`<br>`sentientos/external_model_execution_custody.py`<br>`sentientos/external_model_material.py`<br>`sentientos/context_hygiene/prompt_constraint_verifier.py` | `tests/test_phase41_perception_api.py`<br>`tests/test_persistent_governed_conversation.py`<br>`tests/test_external_model_execution_custody.py`<br>`tests/test_external_model_material.py`<br>`tests/test_phase75_context_hygiene_prompt_boundary_guardrails.py` | SentientOS narrower | Protections are domain-local; no common confidentiality order propagates through every derivation and destination. | Cross-subsystem derived artifacts do not uniformly preserve a confidentiality restriction. | Study a small restriction-carrying envelope only at concrete cross-domain handoffs. | requires_design_decision | high |
| Principal-set propagation | Identity content carries principal sets; combinations union them; destinations authorize every principal. | effect-authority principal binding, session/user identity fields | `sentientos/runtime_admission.py`<br>`sentientos/runtime_grant_policy.py`<br>`sentientos/canonical_memory.py` | `tests/test_runtime_admission.py`<br>`tests/test_runtime_grant_policy.py`<br>`tests/test_persistent_governed_conversation.py` | SentientOS narrower | Existing principals chiefly answer who may perform an effect, not who may receive derived data. | No general datum-recipient principal set, union-on-derivation rule, or destination subset check was found. | Keep disclosure authority separate from effect authority; investigate only where an actual export consumer needs it. | targeted_future_feature | high |
| Restriction-only remote labels | Remote claims may restrict but cannot self-promote trust, reduce confidentiality, or invent principal authority. | external response untrusted metadata, provider response non-authority, exact local admission/configuration binding, model output cannot become authority evidence | `sentientos/external_model_material.py`<br>`sentientos/external_model_execution_custody.py`<br>`sentientos/runtime_admission.py`<br>`sentientos/discernment_synthesis.py` | `tests/test_external_model_material.py`<br>`tests/test_external_model_execution_custody.py`<br>`tests/test_runtime_admission.py`<br>`tests/test_system_phase_authority.py` | equivalent intent / different mechanism | SentientOS enforces non-promotion at hardened authority boundaries but lacks one content-label merge operator. | The invariant is piecemeal and weaker in legacy memory/perception context paths. | Document external material may constrain itself but needs independent local evidence to gain status. | unify_existing_invariant | high |
| Tiered result labeling | Per-item labels, source declarations, hidden-reference labels, and secure defaults have ordered authority. | typed evidence records, local configuration custody, response metadata, World-State source manifests | `sentientos/world_state_board.py`<br>`sentientos/external_model_material.py`<br>`sentientos/external_model_custody.py` | `tests/test_world_state_board.py`<br>`tests/test_external_model_material.py`<br>`tests/test_external_model_custody.py` | SentientOS narrower | SentientOS has exact domain schemas rather than a generic label precedence tier. | No uniform tier-resolution algorithm spans tool/provider/perception outputs. | Prefer explicit local fallback ownership and reject argument-shaped policy claims. | documentation_only | high |
| Conservative propagation | Transformations inherit or restrict source labels, commonly using most-restrictive propagation. | World-State lineage/conflict posture, memory provenance, custody digests, readiness artifact source bindings | `sentientos/world_state_board.py`<br>`sentientos/canonical_memory.py`<br>`sentientos/external_model_material.py`<br>`sentientos/reviewer_proof_bundle.py` | `tests/test_world_state_board.py`<br>`tests/test_persistent_governed_conversation.py`<br>`tests/test_external_model_material.py`<br>`tests/test_reviewer_proof_bundle.py` | FIDES more formal/crisp | Strong newer custody chains preserve exact inputs; legacy summaries can lose event identity and do not propagate privacy uniformly. | No universal derivation monotonicity contract. | Unify laws about authority, provenance loss, currentness, and confidentiality while leaving domains typed. | unify_existing_invariant | high |
| Unlabeled tool output | Unknown output defaults to untrusted integrity. | unknown evidence, provenance-incomplete state, authority-ineligible external data, fail-closed admission | `sentientos/external_model_material.py`<br>`sentientos/world_state_board.py`<br>`sentientos/runtime_admission.py` | `tests/test_external_model_material.py`<br>`tests/test_world_state_board.py`<br>`tests/test_runtime_admission.py` | genuinely orthogonal | SentientOS distinguishes unknown, untrusted, false, stale, and authority-ineligible. | There is no single default for arbitrary unlabeled content. | Default conservatively per consequence: unknown epistemically, ineligible for authority, and privacy-conservative where disclosure is possible. | documentation_only | high |
| Sink policy | Sensitive tools declare integrity, confidentiality, and principal constraints enforced before execution. | ControlPlaneKernel, RuntimeGovernor, runtime grants/admissions, specialized execution custody | `sentientos/control_plane_kernel.py`<br>`sentientos/runtime_governor.py`<br>`sentientos/runtime_admission.py`<br>`sentientos/external_model_execution_custody.py` | `tests/test_control_plane_kernel.py`<br>`tests/test_runtime_governor.py`<br>`tests/test_runtime_admission.py`<br>`tests/test_external_model_execution_custody.py` | SentientOS broader | SentientOS gates exact capability/effect/subject/configuration and operational state, but not a generic content confidentiality label. | Data-disclosure constraints are less uniform than effect admission. | Continue exact domain admission; add no middleware merely for architectural resemblance. | no_change | high |
| Variable indirection | Untrusted raw bytes may remain outside primary model context behind a reference. | opaque credential handles, exact request-material source, artifact references, digest-bound effect custody | `sentientos/external_model_execution_custody.py`<br>`sentientos/external_model_material.py`<br>`sentientos/repository_mutation_handoff.py` | `tests/test_external_model_execution_custody.py`<br>`tests/test_external_model_material.py`<br>`tests/test_repository_mutation_handoff.py` | partially analogous | SentientOS indirection protects credentials/effect material from general cognition; it is not a generic untrusted-content variable store. | No general adversarial-content reference facility for cognition. | Opaque, owner-resolved handles are valuable where a named consumer can operate without model visibility. | targeted_future_feature | high |
| Quarantined LLM | A separate tool-free model inspects hidden content; outputs retain restrictions and cannot declassify. | runtime integrity quarantine, external material transient custody, selective memory/context hygiene | `sentientos/runtime_governor.py`<br>`sentientos/external_model_material.py`<br>`sentientos/context_hygiene/prompt_constraint_verifier.py`<br>`sentientos/selective_memory_distillation_contract.py` | `tests/test_runtime_governor.py`<br>`tests/test_external_model_material.py`<br>`tests/test_phase75_context_hygiene_prompt_boundary_guardrails.py`<br>`tests/test_selective_memory_distillation_contract.py` | no analogue found | Existing quarantine controls admission/integrity or exposure selection; none is an isolated tool-free cognition worker whose output retains source restrictions. | FIDES-style cognitive quarantine is genuinely absent. | Promising only for identified adversarial web/provider/perception paths; it is not universally necessary. | targeted_future_feature | medium |
| Blind forwarding | Hidden references cross permitted paths without revealing raw bytes to primary cognition. | opaque credential use, transient request-material handoff, digest-bound artifacts and file-effect custody | `sentientos/external_model_execution_custody.py`<br>`sentientos/external_model_material.py`<br>`sentientos/builtin_local_effect_runner.py` | `tests/test_external_model_execution_custody.py`<br>`tests/test_external_model_material.py`<br>`tests/test_builtin_local_effect_runner.py` | SentientOS broader | Effect custody can be stronger and more exact than FIDES generic hidden variables, but generic cognitive forwarding is absent. | No general hidden-content forwarding path across arbitrary cognition tools. | Preserve raw-byte separation where deterministic owners can resolve exact handles. | no_change | high |
| Exact approval binding | Approval binds the exact resolved invocation in its owning session; edits require new approval. | request/configuration digest admission binding, principal/effect/subject binding, exact memory retention receipt | `sentientos/runtime_admission.py`<br>`sentientos/external_model_execution_custody.py`<br>`sentientos/canonical_memory.py` | `tests/test_runtime_admission.py`<br>`tests/test_external_model_execution_custody.py`<br>`tests/test_persistent_governed_conversation.py` | equivalent intent / different mechanism | SentientOS binding uses explicit domain identities and sequence validity rather than a single session invocation occurrence. | No gap on hardened traced paths; legacy approval-like records vary. | Keep exact resolved-content/configuration binding as a reusable invariant. | documentation_only | high |
| One-shot approval | Invocation approval is consumed once. | fulfillment authorization consumption, idempotency/replay controls, runtime admission validity windows | `sentientos/fulfillment_authorization.py`<br>`sentientos/runtime_admission.py`<br>`sentientos/external_model_execution_custody.py` | `tests/test_fulfillment_authorization.py`<br>`tests/test_runtime_admission.py`<br>`tests/test_external_model_execution_custody.py` | unresolved | Fulfillment consumption is single-use in its domain; RuntimeAdmissionVerifier has no consumption ledger and permits repeat verification while valid. | External-model AdmissionEvidence can authorize repeated attempts for the same exact request/configuration within sequence lifetime; intent is ambiguous. | Decide reuse versus one-shot per effect and specify durable attempt/receipt recovery before changing semantics. | requires_design_decision | high |
| Session security state | Labels, variables, audits, and approvals belong to an owning session. | conversation/session identity, runtime generation, operator principal, admission sequence, provider invocation, resident lifetime | `sentientos/canonical_memory.py`<br>`sentientos/runtime_admission.py`<br>`sentientos/external_model_execution_custody.py`<br>`sentientos/maintenance_resident_runtime_adoption.py` | `tests/test_persistent_governed_conversation.py`<br>`tests/test_runtime_admission.py`<br>`tests/test_external_model_execution_custody.py`<br>`tests/test_maintenance_resident_runtime_adoption.py` | SentientOS broader | SentientOS scopes different security facts to precise domain identities rather than one universal session. | No missing universal session abstraction is established. | Do not collapse generation, principal, admission, conversation, and invocation identity. | incompatible_or_not_useful | high |
| Audit | Blocked and approval-gated operations produce explicit audit state. | hash-linked audit, audit-trust runtime, effect/denial receipts, grant/admission ledgers, World-State projections | `sentientos/audit/__init__.py`<br>`sentientos/audit_trust_runtime.py`<br>`sentientos/runtime_admission.py`<br>`sentientos/world_state_board.py` | `sentientos/tests/test_audit_chain.py`<br>`tests/test_degraded_audit_trust_propagation.py`<br>`tests/test_runtime_admission.py`<br>`tests/test_world_state_board.py` | SentientOS broader | SentientOS audit integrity can itself constrain authority and has specialized durable receipts; coverage remains surface-specific. | No distinct FIDES audit invariant is missing beyond consistent denial/attempt coverage. | Retain stage-specific receipts and make gaps explicit rather than adopting a simpler log. | no_change | high |
| Conservative-taint tradeoff | Whole-context taint is safe but can reduce utility; finer scoping/decay remains open. | fact/event/fragment/evidence granularity, selective memory, typed World-State facts | `sentientos/world_state_board.py`<br>`sentientos/perception_api.py`<br>`sentientos/selective_memory_distillation_contract.py`<br>`sentientos/canonical_memory.py` | `tests/test_world_state_board.py`<br>`tests/test_phase41_perception_api.py`<br>`tests/test_selective_memory_distillation_contract.py`<br>`tests/test_persistent_governed_conversation.py` | SentientOS broader | SentientOS already uses domain-specific item granularity; it has no whole-context generic taint to decay. | Response/material-level restrictions do not consistently survive derivation. | Use the smallest current consumer-owned unit: fact, event, memory fragment, response material, or claim/evidence—not arbitrary JSONPath. | requires_design_decision | high |

## Integrity analysis

SentientOS has no generic cross-domain integrity bit. That is mostly intentional: audit trust asks whether an append-only record chain is intact; evidence strength asks what a World-State fact supports; provenance asks where bytes/claims came from; calibration expresses sensor/model uncertainty; currentness asks whether evidence is timely; model-output trust marks epistemic status; authority decides whether a bounded effect may proceed. Collapsing them into `trusted` would lose actionable distinctions. A useful unifying law is narrower: **derivation and external assertion cannot increase authority/trust status without independent evidence recognized by the owning domain**. This adds clarity without adding a label ontology.

## Confidentiality and principal analysis

Perception carries `privacy_class`; canonical memory has explicit retention/protection admission; legacy/selective memory limits selection but is not a universal secrecy calculus; credentials are resolved behind opaque handles and transient read-only views; context-hygiene artifacts prohibit prompt/provider actions on review-only paths; external request/response buffers are digest-checked, briefly exposed, and cleared best-effort; publication/export paths use specialized review and custody. These controls remain local. No repository-wide rule proves that a privacy restriction follows every summary, World-State projection, response consumer, or exported artifact.

**Critical distinction:** runtime grants/admissions bind the principal permitted to request an effect. They do not encode a general set `{A, B}` of principals permitted to receive a datum, and no general union-on-derivation rule was found. Principal-scoped data confidentiality is therefore a genuine narrower area, not a missing authority feature.

## Provenance and derivation analysis

| Candidate law | Classification | Evidence-based finding |
|---|---|---|
| derivation cannot manufacture authority | **true on hardened surfaces only** | All traced authority gates demand independent typed admission; legacy text can influence candidates but not satisfy a gate. |
| derivation cannot manufacture provenance | **true on hardened surfaces only** | Digest-bound custody preserves sources; legacy perception aggregation and memory summaries can lose exact source identity. |
| interpretation cannot manufacture observation | **true on hardened surfaces only** | World-State and host gates retain types; legacy narrative context is not uniformly labeled interpretation. |
| derivation cannot silently reduce confidentiality | **desirable but unimplemented** | Privacy and secrecy controls exist, but no cross-domain propagation contract was found. |
| staleness cannot improve without new evidence | **true on hardened surfaces only** | Freshness is explicit in newer gates; legacy timestamp coercion and relevance ranking are weaker. |
| untrusted external material cannot self-promote | **true on hardened surfaces only** | External-model material is explicitly non-authoritative; no universal law covers every legacy ingress. |
| lossy derivation must disclose provenance loss | **false** | Newer artifacts disclose sources, while legacy summaries need not enumerate source digests. |

Path trace: observation→aggregate and observation→World-State retain typed facts but legacy narrative aggregation can omit exact event digests; memory→summary/context can drop interpretation labels and uses relevance rather than truth/currentness; request material→provider is exact-digest admitted and transient; provider response→consumer is explicitly `untrusted_external_data`; evidence→proposal does not grant effect authority; source artifacts→readiness/review artifacts are strong where schemas bind digests, but metadata-only readiness remains non-authority. The smallest useful granularity is the consumer-owned fact, perception event, memory fragment, response material, or claim/evidence record—not arbitrary JSONPath labels.

## Quarantine and indirection analysis

SentientOS runtime/integrity quarantine means denial/restriction after malformed or unsafe runtime behavior. It is not FIDES cognitive quarantine. External-model request material and credentials are hidden behind exact bindings, exposed transiently only to deterministic transport consumers, and cleared; memory selection and context hygiene reduce exposure; raw perception retention defaults off. None of these invokes a separate tool-free model over an opaque untrusted variable while propagating the original restriction to its summary. Thus cognitive quarantine is **genuinely absent** and a **promising future mechanism** only for a proven adversarial ingestion consumer.

Blind forwarding is different: SentientOS already does it strongly for credentials, request material, artifact digests, and effect custody. Raw bytes need not enter stochastic cognition for a deterministic transport/effect owner to use them. Generic blind forwarding between cognition tools is absent.

## Admission and approval consumption analysis

| Domain | Current semantics |
|---|---|
| local authorization grants | Reusable only within exact scope and validity until revoked/superseded; grant evidence is not effect proof. |
| host fulfillment authorization consumption | Domain-specific single-use consumption evidence; separate from fulfillment/effect proof. |
| runtime admissions | Exact principal/effect/subject/configuration binding and sequence lifetime; verifier is reusable and has no consumption ledger. |
| external-model admissions | The same exact valid AdmissionEvidence can be verified for multiple transport attempts; ambiguous design decision, not proven one-shot. |
| memory approvals/admissions | Canonical retention binds exact session/turn/request/operation/text; operation-derived identity supplies idempotency, not a generic FIDES approval. |
| maintenance authorities/admissions | Domain-specific leases, predecessor/generation and adoption bindings; revocation/supersession semantics are not reducible to session approval. |

The decisive external-model finding is implementation-level: `RuntimeAdmissionVerifier.verify` checks exact capability, principal, effect, subject, configuration digest, and sequence validity, but records no consumption. `ExternalModelInferenceController.execute` verifies that same evidence on each call and its receipt store does not reject a previously used admission ID. Therefore the same still-valid admission can authorize more than one transport attempt for the same exact request/configuration. The repository does not make that intent clear; classification is **ambiguous / design decision required**, not automatically defective. FIDES one-shot approval cannot be copied without deciding retry semantics and durable recovery.

## Crash-window analysis

| Window | Consequence to resolve before any one-shot change |
|---|---|
| authority issued before consumption | unused durable authority may remain valid until expiry/revocation |
| consumed before execution | one-shot authority may be lost without a durable recoverable intent |
| execution begins before attempt recorded | duplicate-effect ambiguity after restart |
| provider/backend responds before receipt construction | effect may have occurred without a local result record |
| receipt constructed before durable persistence | response known in process but absent after crash |
| receipt persisted | hash-linked custody supports reconstruction, subject to atomic writer guarantees |

SentientOS hash-linked and atomic receipt stores improve restart reconstruction only after persistence. The external-model controller currently performs transport before constructing/appending its receipt, leaving an effect-without-receipt crash window. A future one-shot rule would also introduce consumed-without-effect risk unless authority intent, attempt identity, outcome reconciliation, and idempotency are durably staged. This audit does not redesign that protocol.

## Unknown and unlabeled semantics

FIDES secure-default “untrusted” should not become a universal SentientOS truth value. Depending on consequence, unlabeled input should remain epistemically unknown, provenance-incomplete, authority-ineligible, and privacy-conservative. Unknown is not false; untrusted is not false; stale is not false; and an authority-ineligible claim may still be useful advisory evidence.

## What FIDES teaches SentientOS

1. A documented restriction-only rule could unify hardened external/provider/model boundaries without a label lattice.
2. Cross-domain derived artifacts need an explicit answer about confidentiality preservation.
3. Principal-scoped disclosure is distinct from effect authority and deserves consumer-driven research.
4. Exact approval binding is already a good SentientOS pattern; reuse/consumption must be explicit per domain.
5. Hidden-reference cognition may help specific adversarial-byte paths, while existing deterministic blind custody should be recognized rather than rebuilt.

## What SentientOS should explicitly NOT copy

* No universal `ContentLabel`, trusted/untrusted bit, or global most-restrictive merge.
* No assumption that every admission is one-shot or every raw external byte must be hidden.
* No conflation of effect principal with datum recipient, approval with admission, or session with generation/resident lifetime.
* No middleware transplant merely because Agent Framework uses middleware.
* No claim that summarization declassifies, memory proves current truth, proposal grants authority, or remote metadata promotes itself.

## Design questions requiring operator/architect decision

1. Should a written cross-domain non-promotion law govern authority, trust, provenance, and freshness while retaining separate types?
2. Which concrete export/summary consumers require confidentiality propagation and datum-recipient sets?
3. For external-model inference, is exact AdmissionEvidence deliberately retryable during its sequence lifetime or should an attempt consume it?
4. If one-shot, what durable intent/attempt/result/receipt recovery state and provider idempotency key are required?
5. Which named ingestion path, if any, justifies isolated tool-free cognition and inherited restrictions?

## Ranked-by-dependency future research questions

This ordering expresses logical dependency, **not** implementation order or priority.

1. Define vocabulary boundaries among epistemic status, provenance, confidentiality, and authority.
2. Prove where current derivations preserve or lose those dimensions.
3. Identify actual destination consumers needing datum-recipient policy.
4. Decide external-model retry/idempotency semantics from effect and recovery requirements.
5. Model crash recovery for any selected one-shot authority.
6. Evaluate cognitive quarantine only against a named adversarial-byte flow after its disclosure and derivation requirements are known.

## Evidence appendix

Primary SentientOS indexes: `architecture/current_repository_system_atlas.json`, `docs/architecture/current_repository_system_atlas.md`, `docs/architecture/authoritative_state_evidence_custody.md`, `README.md`, `docs/architecture/public_technical_overview.md`, and `SEMANTIC_GLOSSARY.md`. Every crosswalk source/test path is machine-checked by the companion structural test. The structured companion is `architecture/fides_sentientos_comparative_invariant_audit.json`. Tests validate shape and evidence-path existence only; they deliberately do not pretend to prove subjective semantic comparisons.

### Explicit confirmations

* No runtime semantics or authority semantics changed.
* No FIDES mechanism was copied merely because it exists.
* Analogues were searched before gaps were declared; legacy and modern paths were distinguished.
* Principal data confidentiality was not conflated with effect authority.
* Unknown and untrusted were not conflated with false.
* Approval was not conflated with admission, and admission was not assumed one-shot without evidence.
* Every recommendation is research/design-only and uses the closed vocabulary.
