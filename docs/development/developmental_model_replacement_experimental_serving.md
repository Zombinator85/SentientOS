# Developmental model-replacement experimental serving

The bounded runtime composes this exact chain:

```text
hardened commissioned evidence A/B
  -> read-only CognitiveModelIdentity projection
  -> persisted, preregistered ModelReplacementProtocol
  -> digest-bound runtime operator approval
  -> independent MODEL_SERVING admission
  -> experiment-scoped exact-runtime worker
  -> observed identity == preregistered identity
  -> independent LOCAL_MODEL_INFERENCE admission for every call
  -> DevelopmentalModelReplacementExperiment
  -> bounded unload and immutable closure receipt
```

The protocol loader requires the exact ID and digest of an existing canonical protocol
artifact and verifies all protocol semantics. It never creates or repairs a protocol.
The commissioning reader accepts production evidence only from authenticated
`local-model/commissioning/receipts/` custody, verifies the hardened v3 lineage,
current catalog provenance and no-follow artifact bytes, and rejects synthetic evidence
unless the controller's explicit test-only switch is enabled.

## Identity projection

The canonical projection binds the authority-map model ID, semantic artifact identity,
content SHA-256 and size, sidecar digest, configuration digest, runtime family, candidate
index, production/non-fallback posture, and the complete observed active-model identity.
The active identity digest is SHA-256 over that canonical semantic mapping. The authority
record payload is exactly `{model_id, authority_map_digest,
observed_active_model_identity}` in canonical sorted compact JSON. Its SHA-256-prefixed
digest is `authority_record_digest`; `authority_record_id` is
`commissioned-authority-record-` plus its first 24 hexadecimal digits. The same rule is
used before and after load, and exact `CognitiveModelIdentity` equality is required.

## Authority and custody

The serving action is `load_preregistered_experimental_local_model`, its principal is
`deterministic_developmental_model_replacement_experimental_serving_controller`, and
its correlation is the caller-supplied exact serving correlation bound into intent and
approval. Approval is consumed under
`sentientos.developmental_model_replacement_experimental_serving_approval:v1`.
Intent, successful serving, and closure/invalidation use respectively
`sentientos.developmental_model_replacement_experimental_serving_intent:v1`,
`sentientos.developmental_model_replacement_experimental_serving_receipt:v1`, and
`sentientos.developmental_model_replacement_experimental_serving_closure:v1`.

Approval, protocol, receipt, artifact, runtime, and load configuration are reverified
immediately before load. Serving construction performs zero inference and grants no
inference authority. Each endpoint call uses the ordinary governed invoker with purpose
`resident_developmental_model_replacement_experiment`, an independent
`LOCAL_MODEL_INFERENCE` admission, the existing per-correlation budget, and forced
`temperature = 0`. Pre/post generation guards withhold stale output and invalidate and
unload a changed lifetime. Close is idempotent and produces one bounded-unload receipt.

Canonical activation: **unchanged**. Canonical production serving: **unchanged**.
Resident default model: **unchanged**. Developmental history: **unchanged by serving
itself**. All experimental custody is physically separate beneath
`local-model/developmental-model-replacement/experimental-serving/`.

An experiment result is evidence, not an identity conclusion. This implementation does
not claim a real repeated production campaign, resident A-to-B transition, learning,
selfhood, sentience, consciousness, or model-independent identity.
