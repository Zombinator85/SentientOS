# Governed External-Model Inference Authority Definition

## Status and non-authority boundary

This document preserves the exact operator-approved authority definition now
registered in the canonical task-authority catalog. Registration is governance
metadata only: it does **not** issue a runtime operator grant, issue runtime
admission, resolve a credential, select live transport, contact a service, or
change runtime authority.

The registered definition digest is
`539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c` and its
operator approval evidence ID is
`approval:external_model_inference:539ff509bbea:001`. The definition is not
enabled, granted, active, transport-ready, credential-ready, or production-ready.

The former definition digest
`0b74d6b113f909e9157263b6321864a4bd50a97d8e9ffda080bb21fcd02dcb6c`
is superseded and invalid for approval. It is not a compatibility identity.

## A. Proposed capability ID

`external_model_inference`

The identifier remains stable and accurately names the one effect boundary.
The execution-custody controller already uses it as `ADMISSION_KIND`; no second
capability or generic provider/network capability is needed.

## B. Purpose

> Permit a separately granted and admitted deterministic external-model
> inference controller to perform one configuration-bound invocation of an
> enabled external-model service at its exact HTTPS endpoint for an allowed
> model and bounded request, using its service-bound opaque credential
> reference when configured, and to custody the result and durable invocation
> receipt, without granting generic network, credential-administration,
> provider-administration, cognition-trust, grant-issuance, or
> admission-issuance authority.

## C. Exact subsystem kinds

`frozenset({"external_model_inference"})`

This is the narrow repository-native execution domain used by the controller's
admission capability identity. It is not a generic network, provider, or model
subsystem.

## D. Exact principal kinds

`frozenset({"deterministic_external_model_inference_controller"})`

`PrincipalIdentity` and `ExternalModelInferenceController` implement this
principal kind. The principal is not prompt content, model output, a service,
credential, adapter, or response. The controller receives only a verifier; it
does not hold `RuntimeGrantAuthority`, `RuntimeGrantPolicy`, or
`RuntimeAdmissionAuthority`. It therefore cannot create or broaden a grant,
issue admission, or alter an authority definition.

## E. Exact effect set

`frozenset({"bounded_external_model_network_egress"})`

This is the exact effect identity implemented by `RequiredEffectDescription`
and consumed by `RuntimeAdmissionVerifier` immediately before the isolated
transport boundary. It is intentionally the sole authority effect:

* configured service, exact endpoint, allowed model, optional service-bound
  credential reference, bounded request, and configuration digest are narrower
  bindings of this effect, not independently executable effects;
* result custody and hash-linked receipt persistence are mandatory controller
  consequences and evidence, not extra authority grants; and
* invented effect names from the superseded proposal are removed because the
  current runtime does not consume them.

The effect cannot authorize generic network access. The verifier requires the
exact subject `service_id:endpoint_id` and the digest of the exact request
binding plus exact configured-service digest. The service catalog independently
requires HTTPS, forbids redirects and wildcard hosts/paths/models, and requires
the selected endpoint, model, and credential-reference identity to equal the
enabled configured entry.

## F. Exact affirmative preconditions

The definition's ordered `required_goal_phrases` are:

```text
explicit operator approval of definition registration
exact registered external model inference definition
authenticated bounded operator runtime grant
admitted deterministic external model inference controller
enabled configured external model service
exact service endpoint model request and configuration binding
service bound opaque credential reference when configured
valid runtime grant policy decision
valid bounded runtime admission
request provenance
durable hash linked invocation receipt
```

The definition's ordered `approval_requirements`, which must be supplied
exactly as `RuntimeGrantRequest.affirmative_preconditions`, are:

```text
authenticated bounded operator runtime grant
enabled configured external model service
exact service endpoint model request and configuration binding
service bound opaque credential reference when configured
valid runtime grant policy decision
valid bounded runtime admission
request provenance
durable hash linked invocation receipt
```

These phrases describe checks that exist in the current chain. Definition
registration has separate digest-bound operator evidence. `RuntimeGrantAuthority`
validates separately authenticated grant evidence and definition narrowing;
`RuntimeGrantPolicy` validates grant lifetime, epoch, revocation, principal,
effect, subject, request/configuration digest, and admission lifetime;
`RuntimeAdmissionAuthority` issues evidence only after that policy path;
`RuntimeAdmissionVerifier` validates exact stored evidence and its bindings;
the catalog and custody registry validate configuration and request bindings;
and the controller writes the correlated receipt before returning or reporting
null-transport unavailability.

## G. Exact forbidden scope

The ordered `forbidden_goal_phrases` are:

```text
arbitrary network authority
arbitrary internet access
arbitrary host
arbitrary url
arbitrary endpoint
credential creation
credential modification
credential rotation
credential inspection
credential export
credential administration
provider administration
provider account administration
billing administration
account administration
shell authority
shell execution
arbitrary subprocess authority
arbitrary subprocess execution
unrelated filesystem mutation
repository mutation
maintenance authority
runtime adoption
host actuation
device actuation
capability definition mutation
capability self modification
grant issuance
admission issuance
self grant
model output authorization
cognition authorization
configuration authorization
credential possession authorization
service availability authorization
response receipt cognition trust
```

No field contains a wildcard. In addition to documenting the maximum scope,
these phrases participate in the repository's forbidden-goal checks; runtime
admission also rejects a forbidden phrase in its scoped subject/provenance.
Configuration, credential-reference existence or availability, response
receipt, and model output remain evidence/data and cannot authorize themselves.

## H. Definition, grant, admission, and execution narrowing

The implemented ladder is:

```text
registered definition (maximum kind/effect vocabulary; grants nothing)
  -> authenticated RuntimeOperatorGrant (one definition digest/version,
     subsystem, principal, effect subset, exact subjects, optional exact
     request/configuration digests, epoch, and bounded sequence interval)
  -> RuntimeGrantPolicy (fails closed on drift, expiry, revocation, unavailable
     policy, or any attempted broadening)
  -> RuntimeAdmissionAuthority (durable exact grant-bound admission)
  -> RuntimeAdmissionVerifier (issuer, ledger, definition, principal, effect,
     subject, request/configuration digest, lifetime, revocation and
     supersession checks)
  -> ExternalModelInferenceController (catalog/request/credential-handle checks)
  -> ExternalModelTransport effect boundary
```

Thus **definition != grant**, **grant != admission**, **admission !=
execution**, and **execution != success**. A grant is equal to or narrower than
the definition; an admission is equal to or narrower than its grant. Grant
revocation prevents later issuance. Issued admissions separately expire and
can be revoked or superseded.

For an invocation, `subject_id` is exactly `service_id:endpoint_id` and
`request_configuration_digest` is the digest of:

```python
{"request": request.binding_digest, "configuration": entry.configuration_digest}
```

The request binding includes service, endpoint, credential-reference identity,
model, payload digest, generation parameters, provenance, principal, required
effect, sequence, and schema. The configuration binding includes the exact
service and HTTPS endpoint identity, permitted model set, configured opaque
credential reference, enabled state, provenance, and version. Caller-supplied
arbitrary endpoints therefore cannot become authorized merely by naming this
capability.

Credential-reference existence is not authority to use it. An admitted,
configuration-bound invocation may carry only the matching opaque use handle;
that use authority is not inspection, export, enumeration, creation,
modification, rotation, or administration of secret material.

Receipt fields separately record request admission, transport attempt,
transport success, provider response, response digest, synthetic status, and
whether an effect occurred. A received response is never marked trusted or
accepted by cognition.

## I. Remaining implementation prerequisites

These prevent a live actuator, but do not make this non-granting definition
structurally ambiguous:

1. Governed, read-only production credential resolution now exists through the
   OS keyring backend and exact admitted-invocation resolver. Provider-specific
   authentication framing and live transport remain unimplemented.
2. `NullExternalModelTransport` is the sole production transport. An audited
   adapter that enforces the already-bound exact HTTPS identity without
   redirects or other egress is required before live invocation.
3. The external-model path has no concrete `RuntimeGovernor` operational
   feasibility predicate. `RuntimeGrantPolicy` only accepts a fail-closed
   `policy_available` input; a real deployment must define and connect the
   operational predicate before transport rather than treating authority as
   feasibility.
4. Response acceptance by cognition remains a separate, unimplemented trust
   decision. A transport response or persisted digest must never imply it.

`ControlPlaneKernel` has no implemented role in this effect path and is not
included ceremonially. Runtime grant policy and admission authority own the
authority decision; the controller/verifier/catalog own final binding checks;
the future adapter must own enforcement at the transport boundary.

Registration before those actuator pieces exist is responsible because
registration grants nothing and the current production adapter cannot perform
an effect. Runtime exercise would remain premature.

## J. Registration judgment

The definition is **registered as definition-only governance metadata**. It is
**not actuator-ready**, and its registration is neither a runtime grant nor a
runtime admission.

Readiness answers:

1. **Real subsystem and principal?** Yes. The admission identity and controller
   principal are implemented.
2. **Exact non-wildcard effect?** Yes: one implemented effect identity.
3. **Clean definition/grant/admission narrowing?** Yes.
4. **Arbitrary internet egress?** No; exact subject, request/configuration
   digest, catalog identity, HTTPS endpoint, and no-redirect checks constrain it.
5. **Arbitrary credential administration?** No.
6. **Can cognition/model output self-authorize?** No.
7. **Can configuration self-authorize?** No.
8. **Can credential possession self-authorize?** No.
9. **Endpoint scope enforceable?** Yes, deterministically through endpoint,
   catalog, subject, and digest checks. A future live adapter must preserve it.
10. **Request/configuration binding enforceable?** Yes.
11. **Can grants expire/revoke?** Yes.
12. **Can admissions expire/revoke/supersede?** Yes.
13. **Durable execution evidence?** Yes; receipts are atomic, correlated,
   hash-linked, and restart-validated.
14. **Response trust separate from transport success?** Yes; custody records no
   cognition-acceptance claim.
15. **Non-blocking missing pieces?** Live transport, provider authentication framing, a
   concrete external-model operational-feasibility predicate, and response
   trust policy.
16. **Definition-approval blockers?** None. The exact endpoint/effect/request
   semantics required by the definition are representable and enforced before
   the null transport boundary. The missing pieces block execution, not
   definition registration.

## K. Canonical serialized definition

The registration algorithm sorts set-valued fields, preserves tuple ordering,
then applies `json.dumps(payload, sort_keys=True, separators=(",", ":"))`
without a trailing newline:

```json
{"approval_requirements":["authenticated bounded operator runtime grant","enabled configured external model service","exact service endpoint model request and configuration binding","service bound opaque credential reference when configured","valid runtime grant policy decision","valid bounded runtime admission","request provenance","durable hash linked invocation receipt"],"capability_id":"external_model_inference","forbidden_goal_phrases":["arbitrary network authority","arbitrary internet access","arbitrary host","arbitrary url","arbitrary endpoint","credential creation","credential modification","credential rotation","credential inspection","credential export","credential administration","provider administration","provider account administration","billing administration","account administration","shell authority","shell execution","arbitrary subprocess authority","arbitrary subprocess execution","unrelated filesystem mutation","repository mutation","maintenance authority","runtime adoption","host actuation","device actuation","capability definition mutation","capability self modification","grant issuance","admission issuance","self grant","model output authorization","cognition authorization","configuration authorization","credential possession authorization","service availability authorization","response receipt cognition trust"],"principal_kinds":["deterministic_external_model_inference_controller"],"purpose":"Permit a separately granted and admitted deterministic external-model inference controller to perform one configuration-bound invocation of an enabled external-model service at its exact HTTPS endpoint for an allowed model and bounded request, using its service-bound opaque credential reference when configured, and to custody the result and durable invocation receipt, without granting generic network, credential-administration, provider-administration, cognition-trust, grant-issuance, or admission-issuance authority.","required_effects":["bounded_external_model_network_egress"],"required_goal_phrases":["explicit operator approval of definition registration","exact registered external model inference definition","authenticated bounded operator runtime grant","admitted deterministic external model inference controller","enabled configured external model service","exact service endpoint model request and configuration binding","service bound opaque credential reference when configured","valid runtime grant policy decision","valid bounded runtime admission","request provenance","durable hash linked invocation receipt"],"subsystem_kinds":["external_model_inference"]}
```

Any modification to any definition field or ordered phrase requires a new
digest and new approval evidence.

## L. New SHA-256 definition digest

```text
539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c
```

This is a new digest; the old
`0b74d6b113f909e9157263b6321864a4bd50a97d8e9ffda080bb21fcd02dcb6c`
digest is superseded and invalid for approval.

## M. Exact operator-approval template

The later introducing task identity is exactly
`register_governed_external_model_inference_authority_definition`. The operator
must supply both identified values and compute `evidence_digest` with
`operator_approval_evidence_digest` after substitution. Placeholders are not
approval.

```json
{"approval_status":"approved","approved_capability_id":"external_model_inference","approved_definition_digest":"539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c","approved_task_name":"register_governed_external_model_inference_authority_definition","evidence_digest":"<COMPUTE_AFTER_OPERATOR_VALUES_ARE_SUPPLIED>","evidence_id":"<OPERATOR_SUPPLIED_EVIDENCE_ID>","operator_identity_label":"<OPERATOR_SUPPLIED_IDENTITY_LABEL>","schema_version":"sentientos.authority_definition_operator_approval:v1"}
```

This evidence approves only definition registration. It is not a runtime grant,
admission, endpoint approval, credential-use approval, or invocation approval.

## N. Exact later registration inputs

After genuine operator evidence is supplied, a separate task may pass this
definition-only structure to `register_authority_definition`:

```python
{
    "task_classification": "authority_definition_registration",
    "task_name": "register_governed_external_model_inference_authority_definition",
    "definitions": [
        TaskAuthorityDefinition(
            capability_id="external_model_inference",
            subsystem_kinds=frozenset({"external_model_inference"}),
            principal_kinds=frozenset({"deterministic_external_model_inference_controller"}),
            required_effects=frozenset({"bounded_external_model_network_egress"}),
            required_goal_phrases=(
                "explicit operator approval of definition registration",
                "exact registered external model inference definition",
                "authenticated bounded operator runtime grant",
                "admitted deterministic external model inference controller",
                "enabled configured external model service",
                "exact service endpoint model request and configuration binding",
                "service bound opaque credential reference when configured",
                "valid runtime grant policy decision",
                "valid bounded runtime admission",
                "request provenance",
                "durable hash linked invocation receipt",
            ),
            forbidden_goal_phrases=(
                "arbitrary network authority", "arbitrary internet access",
                "arbitrary host", "arbitrary url", "arbitrary endpoint",
                "credential creation", "credential modification",
                "credential rotation", "credential inspection",
                "credential export", "credential administration",
                "provider administration", "provider account administration",
                "billing administration", "account administration",
                "shell authority", "shell execution",
                "arbitrary subprocess authority",
                "arbitrary subprocess execution",
                "unrelated filesystem mutation", "repository mutation",
                "maintenance authority", "runtime adoption", "host actuation",
                "device actuation", "capability definition mutation",
                "capability self modification", "grant issuance",
                "admission issuance", "self grant",
                "model output authorization", "cognition authorization",
                "configuration authorization",
                "credential possession authorization",
                "service availability authorization",
                "response receipt cognition trust",
            ),
            approval_requirements=(
                "authenticated bounded operator runtime grant",
                "enabled configured external model service",
                "exact service endpoint model request and configuration binding",
                "service bound opaque credential reference when configured",
                "valid runtime grant policy decision",
                "valid bounded runtime admission",
                "request provenance",
                "durable hash linked invocation receipt",
            ),
            purpose="Permit a separately granted and admitted deterministic external-model inference controller to perform one configuration-bound invocation of an enabled external-model service at its exact HTTPS endpoint for an allowed model and bounded request, using its service-bound opaque credential reference when configured, and to custody the result and durable invocation receipt, without granting generic network, credential-administration, provider-administration, cognition-trust, grant-issuance, or admission-issuance authority.",
        )
    ],
    "operator_approval": {
        "schema_version": "sentientos.authority_definition_operator_approval:v1",
        "evidence_id": "<OPERATOR_SUPPLIED_EVIDENCE_ID>",
        "operator_identity_label": "<OPERATOR_SUPPLIED_IDENTITY_LABEL>",
        "approval_status": "approved",
        "approved_capability_id": "external_model_inference",
        "approved_definition_digest": "539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c",
        "approved_task_name": "register_governed_external_model_inference_authority_definition",
        "evidence_digest": "<COMPUTE_AFTER_OPERATOR_VALUES_ARE_SUPPLIED>",
    },
    "requested_capability_id": "",
    "authority_principal": "",
    "requested_effects": (),
    "runtime_mutations": (),
    "changed_paths": (
        "sentientos/codex_task_authority_admission.py",
        "tests/test_authority_definition_registration.py",
    ),
}
```

The empty request/principal/effect fields are required registration guards, not
runtime requests.

## Final non-authority confirmation

Exactly one definition, `external_model_inference`, was registered with digest
`539ff509bbeabe50cd2be17adf9ebbe58958e894b3cb6728a5c809a605db7b9c` under
operator approval evidence
`approval:external_model_inference:539ff509bbea:001`. No capability or runtime
grant was issued. No admission was issued. No live transport was installed or
invoked. No remote service was contacted. No credential or secret was read. No
runtime authority or runtime behavior changed.
