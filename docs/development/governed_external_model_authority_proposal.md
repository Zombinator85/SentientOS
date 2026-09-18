# Governed External-Model Inference Authority Proposal

## Status and boundary

This document prepares **one** authority definition for operator review. It does
not add the definition to `AUTHORITY_DEFINITIONS`, grant a capability, register
a transport, approve an endpoint or credential, perform an invocation, or
change runtime behavior. The proposal is **not registration-ready** because the
repository currently has no positive, executable governance contracts for a
real provider transport, an approved endpoint identity, or use of an approved
credential reference.

The proposed capability ID is `external_model_inference`. Its purpose is:

> Permit later exact admission of deterministic runtime machinery to invoke
> one approved external model service for one bounded request through
> separately approved endpoint, credential-reference, and network-effect
> controls, receive the response, and write invocation evidence without
> granting transport, credential administration, provider administration, or
> self-authorization.

## Repository vocabulary findings

The authority-definition registry admits an exact capability, subsystem,
principal, and effect set. Registration requires exactly one definition and
operator evidence bound to its digest and introducing task. Registration is
definition-only and cannot request the capability or runtime mutation.

Repository-native concepts reused unchanged are:

- `exact_operator_approval_evidence_read`, from existing authority definitions;
- the `exact_*_read`, `bounded_*`, and `*_receipt_write` effect naming forms;
- `provider_invocation` and `network_egress` as recognized effect concepts;
- deterministic controller principals; and
- affirmative goal phrases plus explicit forbidden-goal phrases.

No existing principal kind is narrow enough for external-model inference. The
proposed `deterministic_external_model_inference_controller` is therefore a new
principal kind, not an assertion that such a principal is implemented or
admitted. Likewise, the repository's provider custody spine is deliberately
null-only/no-secret/no-endpoint/no-client and its provider invocation readiness
preflight is deliberately non-invocable. The new effect identifiers below make
the missing positive semantics explicit; they do not claim those semantics are
implemented.

## A–G. Exact proposed definition

### A. Capability ID

`external_model_inference`

### B. Purpose

The exact purpose is the single paragraph quoted in the status section.

### C. Subsystem kinds

`frozenset({"external_model_inference"})`

This is a proposed new subsystem kind because no current subsystem kind denotes
governed external inference without conflating it with local-model chat or
model distribution.

### D. Principal kinds

`frozenset({"deterministic_external_model_inference_controller"})`

The principal is deterministic runtime machinery. It is not a model, model
output, prompt, provider, credential, configuration, response, or service
availability signal.

### E. Required effects

```text
bounded_approved_external_model_network_egress
bounded_external_model_inference_invoke
exact_approved_external_model_credential_reference_use
exact_approved_external_model_endpoint_identity_read
exact_approved_external_model_service_identity_read
exact_external_model_inference_request_read
exact_operator_approval_evidence_read
external_model_inference_effect_receipt_write
external_model_inference_response_receive
```

`exact_operator_approval_evidence_read` is existing vocabulary. The other eight
effect IDs are proposed vocabulary whose positive enforcement is presently
absent. In particular, `bounded_outbound_transfer` is not reused: by itself it
does not express an approved inference service, endpoint identity, request, or
credential-reference binding and would make this proposal overbroad.

### F. Required affirmative preconditions

These are the exact `required_goal_phrases`, in order:

```text
explicit operator approval
admitted external model inference definition
admitted deterministic runtime principal
approved external model service and endpoint identity
approved credential reference when required
bounded inference request
separate network effect admission
request provenance
no secret disclosure
invocation effect receipt
```

The exact `approval_requirements`, in order, are:

```text
exact operator approval evidence bound to definition digest and introducing task
separately admitted deterministic runtime principal
separately approved service, endpoint, credential-reference, request, and network-effect evidence
immutable invocation effect receipt
```

These strings are admission vocabulary, not enforcement implementations. A
future registration task must not proceed until the positive endpoint,
credential-reference, transport, request, response, and receipt contracts can
actually validate these preconditions.

### G. Forbidden goal phrases

```text
arbitrary internet access
arbitrary host
arbitrary url
arbitrary endpoint
credential creation
credential mutation
credential inspection
credential export
credential rotation
credential administration
provider administration
provider account administration
billing administration
account administration
shell execution
arbitrary subprocess execution
unrelated filesystem authority
repository mutation
host actuation
maintenance authority
runtime adoption
capability self-modification
self-grant
self grant
model output authorization
credential possession authorization
configuration authorization
service availability authorization
```

## H–I. Canonical serialization and definition digest

The registration workflow covers these fields: `capability_id`, sorted
`subsystem_kinds`, sorted `principal_kinds`, sorted `required_effects`, ordered
`required_goal_phrases`, ordered `forbidden_goal_phrases`, ordered
`approval_requirements`, and `purpose`. It serializes that object with
`json.dumps(payload, sort_keys=True, separators=(",", ":"))`, UTF-8 encodes the
result, and takes SHA-256.

The exact canonical serialized definition (one line, with no trailing newline
included in the digest) is:

```json
{"approval_requirements":["exact operator approval evidence bound to definition digest and introducing task","separately admitted deterministic runtime principal","separately approved service, endpoint, credential-reference, request, and network-effect evidence","immutable invocation effect receipt"],"capability_id":"external_model_inference","forbidden_goal_phrases":["arbitrary internet access","arbitrary host","arbitrary url","arbitrary endpoint","credential creation","credential mutation","credential inspection","credential export","credential rotation","credential administration","provider administration","provider account administration","billing administration","account administration","shell execution","arbitrary subprocess execution","unrelated filesystem authority","repository mutation","host actuation","maintenance authority","runtime adoption","capability self-modification","self-grant","self grant","model output authorization","credential possession authorization","configuration authorization","service availability authorization"],"principal_kinds":["deterministic_external_model_inference_controller"],"purpose":"Permit later exact admission of deterministic runtime machinery to invoke one approved external model service for one bounded request through separately approved endpoint, credential-reference, and network-effect controls, receive the response, and write invocation evidence without granting transport, credential administration, provider administration, or self-authorization.","required_effects":["bounded_approved_external_model_network_egress","bounded_external_model_inference_invoke","exact_approved_external_model_credential_reference_use","exact_approved_external_model_endpoint_identity_read","exact_approved_external_model_service_identity_read","exact_external_model_inference_request_read","exact_operator_approval_evidence_read","external_model_inference_effect_receipt_write","external_model_inference_response_receive"],"required_goal_phrases":["explicit operator approval","admitted external model inference definition","admitted deterministic runtime principal","approved external model service and endpoint identity","approved credential reference when required","bounded inference request","separate network effect admission","request provenance","no secret disclosure","invocation effect receipt"],"subsystem_kinds":["external_model_inference"]}
```

Definition SHA-256:

```text
0b74d6b113f909e9157263b6321864a4bd50a97d8e9ffda080bb21fcd02dcb6c
```

Any field or ordering change requires a new digest and new operator approval.

## J. Exact operator-approval evidence template

The later introducing task name is fixed as
`register_governed_external_model_inference_authority_definition`. The operator
must replace both angle-bracket placeholders. After replacement,
`evidence_digest` must be the lowercase SHA-256 of the canonical JSON object
containing every other key below, sorted by key with compact separators. The
placeholder is intentionally not approval and must not be submitted as one.

```json
{"approval_status":"approved","approved_capability_id":"external_model_inference","approved_definition_digest":"0b74d6b113f909e9157263b6321864a4bd50a97d8e9ffda080bb21fcd02dcb6c","approved_task_name":"register_governed_external_model_inference_authority_definition","evidence_digest":"<COMPUTE_AFTER_OPERATOR_VALUES_ARE_SUPPLIED>","evidence_id":"<OPERATOR_SUPPLIED_EVIDENCE_ID>","operator_identity_label":"<OPERATOR_SUPPLIED_IDENTITY_LABEL>","schema_version":"sentientos.authority_definition_operator_approval:v1"}
```

The approval binds only this exact definition and introducing task. It does not
approve an endpoint, credential reference, request, transport implementation,
invocation, or runtime grant.

## K. Subsequent registration-task inputs

Only after the missing contracts below exist and the operator independently
supplies valid approval evidence should a later task submit this exact shape to
`register_authority_definition`:

```python
{
    "task_classification": "authority_definition_registration",
    "task_name": "register_governed_external_model_inference_authority_definition",
    "definitions": [
        TaskAuthorityDefinition(
            capability_id="external_model_inference",
            subsystem_kinds=frozenset({"external_model_inference"}),
            principal_kinds=frozenset({"deterministic_external_model_inference_controller"}),
            required_effects=frozenset({
                "bounded_approved_external_model_network_egress",
                "bounded_external_model_inference_invoke",
                "exact_approved_external_model_credential_reference_use",
                "exact_approved_external_model_endpoint_identity_read",
                "exact_approved_external_model_service_identity_read",
                "exact_external_model_inference_request_read",
                "exact_operator_approval_evidence_read",
                "external_model_inference_effect_receipt_write",
                "external_model_inference_response_receive",
            }),
            required_goal_phrases=(
                "explicit operator approval",
                "admitted external model inference definition",
                "admitted deterministic runtime principal",
                "approved external model service and endpoint identity",
                "approved credential reference when required",
                "bounded inference request",
                "separate network effect admission",
                "request provenance",
                "no secret disclosure",
                "invocation effect receipt",
            ),
            forbidden_goal_phrases=(
                "arbitrary internet access", "arbitrary host", "arbitrary url",
                "arbitrary endpoint", "credential creation", "credential mutation",
                "credential inspection", "credential export", "credential rotation",
                "credential administration", "provider administration",
                "provider account administration", "billing administration",
                "account administration", "shell execution",
                "arbitrary subprocess execution", "unrelated filesystem authority",
                "repository mutation", "host actuation", "maintenance authority",
                "runtime adoption", "capability self-modification", "self-grant",
                "self grant", "model output authorization",
                "credential possession authorization", "configuration authorization",
                "service availability authorization",
            ),
            approval_requirements=(
                "exact operator approval evidence bound to definition digest and introducing task",
                "separately admitted deterministic runtime principal",
                "separately approved service, endpoint, credential-reference, request, and network-effect evidence",
                "immutable invocation effect receipt",
            ),
            purpose="Permit later exact admission of deterministic runtime machinery to invoke one approved external model service for one bounded request through separately approved endpoint, credential-reference, and network-effect controls, receive the response, and write invocation evidence without granting transport, credential administration, provider administration, or self-authorization.",
        )
    ],
    "operator_approval": {  # exact completed object from section J
        "schema_version": "sentientos.authority_definition_operator_approval:v1",
        "evidence_id": "<OPERATOR_SUPPLIED_EVIDENCE_ID>",
        "operator_identity_label": "<OPERATOR_SUPPLIED_IDENTITY_LABEL>",
        "approval_status": "approved",
        "approved_capability_id": "external_model_inference",
        "approved_definition_digest": "0b74d6b113f909e9157263b6321864a4bd50a97d8e9ffda080bb21fcd02dcb6c",
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

The definition digest submitted by that task must recompute to the digest in
section I. Registration must remain separate from any later exact admission,
grant, transport implementation, or invocation.

## L. Readiness check and remaining prerequisites

1. **Is the principal adequately bounded?** Conceptually yes: one deterministic
   controller kind. Mechanically not yet: that principal kind is not implemented
   or admitted.
2. **Is the effect set exact rather than wildcarded?** Yes.
3. **Can arbitrary internet egress occur under this definition?** No by stated
   scope; however, positive endpoint-bound enforcement does not yet exist.
4. **Can arbitrary credential administration occur?** No; only use of an exact
   approved reference is proposed, and all administration is forbidden.
5. **Can model output self-authorize?** No.
6. **Can credentials alone authorize invocation?** No.
7. **Can configuration alone authorize invocation?** No.
8. **Is endpoint identity governable?** Not positively today. Current endpoint
   custody accepts no endpoints and forbids endpoint use.
9. **Is credential use governable separately from credential administration?**
   Not positively today. Current credential custody accepts no secret or
   resolvable credential reference and forbids credential use.
10. **Can successful invocation be distinguished from admission?** The proposed
    invocation and response/receipt effects distinguish them, but no executable
    external-invocation receipt contract exists yet.
11. **Can effect evidence be produced?** Not for a real external invocation
    today; only null/denial metadata exists. The proposed receipt effect requires
    a future immutable receipt contract.
12. **Does a required concept remain unrepresentable?** Yes. Positive governance
    and enforcement are missing for approved service/endpoint identity,
    credential-reference use without credential administration, real transport
    registration, network-effect admission, bounded request/response custody,
    the deterministic principal, and immutable external-invocation receipts.

Therefore this definition is ready for operator **review**, but is explicitly
not ready for operator approval or registration. Before registration, separate
tasks must implement and validate those positive contracts while preserving the
null adapter as the default and without treating metadata, availability,
configuration, credentials, or model output as authority.

## M. Non-authority confirmation

- Nothing was registered.
- No capability was granted.
- No transport was implemented or selected.
- No runtime authority or runtime behavior changed.
- No endpoint, credential, request, or provider was accessed.

