# Developmental model-replacement experimental-serving authority

## Registered authority and implemented bounded runtime

SentientOS has two already-governed cognitive endpoints as inputs to the
model-replacement experiment, while canonical production serving remains bound to the
currently activated hardened model. Real commissioned A/B endpoints use a
bounded runtime bridge that does not mutate canonical activation. The registration remains eligibility metadata; the separately admitted implementation
consumes exact runtime approval and control-plane admission. Registration alone does not
grant authority or perform effects.

The registered authority is limited to exact operator- and protocol-bound
commissioning-evidence reads, exact artifact revalidation, an experiment-scoped model
load, observation of the exact loaded identity, bounded unload, and durable
experiment-scoped serving-receipt custody. Each runtime use obtains an
independent exact `MODEL_SERVING` control-plane admission for each experimental load.
Loading is not cognition authority: every call also requires a separate exact
`LOCAL_MODEL_INFERENCE` admission.

## Runtime chain

```text
exact commissioned model A
        │
        ├─ exact experimental serving admission
        ↓
experiment-scoped worker A
        │
        ├─ separate LOCAL_MODEL_INFERENCE admission per call
        ↓
model-replacement experiment

exact commissioned model B
        │
        ├─ exact experimental serving admission
        ↓
experiment-scoped worker B
        │
        ├─ separate LOCAL_MODEL_INFERENCE admission per call
        ↓
same experiment

Canonical resident production model:
UNCHANGED
```

This is an experimental custody boundary, not a resident cognitive-organ transition.
The worker must be physically separate from canonical production serving: it
must neither replace or invalidate the production chat session, publish itself as
canonical serving, nor become the default resident model. It must not write
`local-model/activation/active.json` or invoke activation compare-and-swap.

## Registration evidence and future approvals

The operator-approved registration is digest-bound to the exact definition and task.
Definition registration satisfies none of the future runtime requirements. Each runtime use requires exact runtime
operator approval bound to the preregistered experiment and model identities, exact
non-synthetic hardened commissioning evidence for production-evidence claims,
separate exact `MODEL_SERVING` and per-call `LOCAL_MODEL_INFERENCE` admissions,
canonical activation and production-serving preservation, bounded unload, and a
durable experiment-scoped serving receipt.

The registered definition remains only eligibility metadata:

- definition does not mean grant;
- definition does not mean load;
- definition does not mean inference;
- definition does not mean activation;
- definition does not mean serving session;
- definition does not mean production evidence.

## Governed invocation boundary

The existing `local_model_authority.py` allowlist includes the purpose
`resident_developmental_model_replacement_experiment`, but
`governed_local_model_invocation.py` includes that purpose in `SUPPORTED_PURPOSES`. The runtime requires the exact production active
identity, temperature zero, and separate inference admission; it must not weaken the
current production-serving invariant.
