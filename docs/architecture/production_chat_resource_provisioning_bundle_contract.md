# Production chat resource provisioning bundle contract

The normative machine artifact is `architecture/production_chat_resource_provisioning_bundle_contract.json` with schema `sentientos.production_chat_resource_provisioning_bundle_contract:v1`. This slice defines a contract only: it adds no producer, bundle write, allocation issuance, root mint, provenance signature, private-key access, authority registration, runtime grant/admission, startup hook, or model invocation.

## Existing consumer and lifecycle separation

The implemented verifier-side consumer reads `sentientos.production_chat_resource_provisioning:v1` at `local-model/resource-provisioning/<resource_provisioning_id>/`. Its fixed objects are `manifest.json`, `root-principal.json`, `root-principal-provenance.json`, `trusted-issuer-catalog.json`, `principal-revocation-registry.json`, `resource-policy.json`, and `resource-ledger.json`. The bounded identifier is path-free: it matches `[a-z0-9][a-z0-9._-]{0,127}\Z`, contains no `..`, and is neither `all` nor `any`.

The consumer authenticates the installation, principal provenance, public issuer trust, currentness, policy, ledger, and one pre-issued allocation. It never calls allocation issuance. Ordinary daemon or serving restart, chat retry, and a new conversation are not producer invocations. Restart therefore reloads the same allocation and conserved entitlement; it cannot replenish it. A missing bundle remains startup failure.

The registered `governed_local_model_resource_allocation_adapter` has exactly five effects: `check_and_debit_governed_local_model_call_entitlement`, `issue_governed_local_model_resource_allocation`, `read_current_causal_resource_principal_evidence`, `read_governed_local_model_resource_policy`, and `write_governed_local_model_resource_consumption_receipt`. It has no create-only installation-state bundle-publication or manifest-finalization effect. It must not be broadened or reinterpreted, so a producer requires separately registered and later admitted authority.

## Eventual producer

`ProductionChatResourceProvisioningBundleProducer` is a future deterministic, explicit, one-time creation operation for principal kind `deterministic_production_chat_resource_provisioning_controller`. It is not startup, inference, or consumption. Its bounded inputs are an authenticated `InstallationStateHandle`, provisioning ID, pre-existing canonical `CausalResourcePrincipal`, pre-existing `RootPrincipalIssuerProvenance`, exact issuer catalog, exact revocation registry, exact `GovernedLocalModelResourcePolicy`, requested `GovernedLocalModelResourceBounds`, requested validity endpoints, and a trusted current-time source. It accepts no caller destination, arbitrary path, environment destination, or chat/session/request data.

The principal, including its immutable `sponsor_evidence_digest`, is already issued. The producer may not call `mint_root` or `mint_root_with_provenance`, renew or derive principals, or alter epoch, sponsorship, or binding. Provenance is also pre-existing. The producer has no `RootIssuerPrivateKeyCustody`, keyring issuer-secret access, raw Ed25519 seed, or signing operation.

Before mutation, `CryptographyEd25519RootIssuerSignatureVerifier` and `RootIssuerProvenanceVerifier` must derive `AuthenticatedRootPrincipalEvidence` from the canonical principal, exact provenance, and exact trusted catalog. Then `PrincipalCurrentnessVerifier` must derive `CurrentAuthenticatedRootPrincipalEvidence` using the exact read-only revocation registry. Caller-authored or serialized evidence cannot substitute. The exact policy's resource kind, allocator, digest, epoch, and validity are verified; the producer neither creates nor widens policy. One trusted canonical UTC instant is shared by principal validity, provenance authentication, currentness, policy validity, and issuance, but is not the later invocation clock.

## Create-only custody, preflight, and publication

The sole destination is `local-model/resource-provisioning/<resource_provisioning_id>/` below the authenticated installation. Concurrent attempts for one ID require deterministic exclusive custody using authenticated installation-state locking or an equivalent fixed lock at `local-model/resource-provisioning-locks/<resource_provisioning_id>.lock`, derived only from the validated ID. A process-local mutex is insufficient; the lock coordinates but grants no entitlement.

Before the first bundle mutation, preflight validates the ID and installation binding; principal canonicality and validity; provenance structure, signature, and issuer trust; revocation/currentness; policy structure, digest, identity, epoch, and validity; requested bounds and validity; and create-only destination state. Under exclusive custody, every one of the seven consumer objects must be absent. Any existing target fails closed. The producer never overwrites, merges, repairs, appends another allocation, silently reuses an ID, automatically retries a partial ID, or cleans/deletes it.

After preflight, the producer creates a durable ledger and calls `GovernedLocalModelResourceAllocator.issue(...)` **exactly once**, bounded by `requested_bounds`, `requested_not_before`, and `requested_not_after`. The allocator remains authoritative for principal binding, currentness, policy ceiling, validity intersection, allocation identity, and digest. Immediately after issuance, the ledger has allocation count 1, attempt count 0, and resource-receipt count 0. The producer neither debits nor infers.

Publication order is: validate inputs; secure exclusive provisioning-ID custody; prove unused; create the durable ledger; issue exactly one allocation; durably create validated non-manifest artifacts; construct the unchanged existing manifest; and durably create `manifest.json` **last**. The manifest is the publication marker. The other immutable objects may have any safe internal order. There is no filesystem-wide atomicity claim. Failure before the manifest leaves an unpublished bundle that the consumer rejects; any created object forbids automatic same-ID retry. An operator may choose a new ID or separately govern cleanup, but cleanup/delete is not producer authority.

The unchanged manifest contains exactly `schema_version`, `provisioning_id`, `installation_identity`, `resource_kind`, `allocator_id`, `principal_id`, `principal_binding_digest`, `provenance_digest`, `trusted_issuer_catalog_version`, `trusted_issuer_catalog_digest`, `revocation_registry_version`, `revocation_registry_digest`, `resource_policy_digest`, `allocation_id`, `allocation_digest`, and `manifest_digest`, using existing `manifest_digest_for(...)`. Consumer reread must preserve principal identity/binding, provenance, catalog version/digest, registry version/digest, policy digest, resource kind, and allocator without translation or weakening.

## Frozen candidate authority

- capability: `production_chat_resource_provisioning_bundle_create`
- subsystem: `causal_resource_principal_architecture`
- principal: `deterministic_production_chat_resource_provisioning_controller`
- effects: `create_only_installation_state_resource_provisioning_bundle`; `finalize_production_resource_provisioning_manifest`; `issue_one_governed_local_model_resource_allocation`; `read_exact_preexisting_causal_resource_principal_artifacts`; `read_exact_resource_trust_currentness_artifacts`; `read_governed_local_model_resource_policy`
- required phrases: `create-only production chat resource provisioning bundle`; `one intentional allocation issuance`; `manifest-last publication`; `restart does not replenish entitlement`
- forbidden phrases: `ordinary startup allocation issuance`; `automatic allocation renewal`; `root principal minting`; `issuer provenance signing`; `private signing key custody`; `overwrite existing provisioning bundle`; `generic installation state mutation`; `arbitrary filesystem mutation`; `model inference`; `grant local model inference`; `network egress`; `host scheduling`
- approvals: `independent operator approval evidence`; `exact definition digest binding`; `exact provisioning identity and installation binding`; `exact pre-existing principal provenance trust and currentness inputs`; `exact resource policy and requested allocation bounds`; `create-only manifest-last publication`
- purpose: `Permit only a deterministic production-chat resource-provisioning controller to verify one pre-existing canonical principal, provenance, trust, currentness, and policy bundle; create one new bounded installation-state provisioning destination; issue exactly one policy-bounded governed local-model resource allocation into its new ledger; and publish the consumer-compatible bundle create-only with manifest last, while granting no root issuance, provenance signing, private-key custody, trust administration, policy administration, model inference or effect authority, arbitrary filesystem mutation, overwrite, or automatic restart issuance.`

Repository-native `authority_definition_digest(...)` yields `132f93c32f5490877a4748c0054dfb66aacb9f2a94ce560d69a0e65337c800f5`.

## Registration handoff and approval template

The future task is exactly `register-production-chat-resource-provisioning-bundle-create-authority-definition`. Its registrar-native object has exactly the keys `task_classification`, `task_name`, `definitions`, `operator_approval`, `requested_capability_id`, `authority_principal`, `requested_effects`, `runtime_mutations`, and `changed_paths`. Classification is `authority_definition_registration`; definitions contains the sole candidate; runtime request fields are respectively `""`, `""`, `[]`, and `[]`. Changed paths are exactly `sentientos/codex_task_authority_admission.py`, `tests/test_authority_definition_registration.py`, and this document. JSON definition collections translate to frozensets and ordered phrase/approval collections to tuples.

The approval template uses `sentientos.authority_definition_operator_approval:v1`, binds approved status, capability, digest, and task, but leaves `evidence_id`, `operator_identity_label`, and `evidence_digest` explicit placeholders. It is not approval evidence and no digest is fabricated while placeholders remain. Registration in a test-only copied catalog grants nothing, performs nothing, and cannot mutate canonical `AUTHORITY_DEFINITIONS`.

## Non-goals and next slice

There is no trust-catalog or revocation administration, policy creation/widening, consumption gate or receipt, model-effect admission/serving/inference, root authority, generic installation/filesystem authority, overwrite, renewal, startup integration, network egress, or host scheduling.

The one selected next slice is: **register the exact production-chat resource-provisioning bundle-create authority definition, contingent on independently supplied approval bound to the frozen candidate digest**. It does not include producer runtime.
