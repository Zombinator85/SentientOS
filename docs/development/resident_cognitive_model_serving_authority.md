# Resident cognitive model serving authority

## Definition-only registration

`resident_cognitive_model_serving` is a governance-only, operator-approved definition for a **future**, separately admitted `deterministic_resident_cognitive_model_serving_controller` in `local_model_chat`. Registration grants no capability or runtime authority, performs no effect or runtime mutation, constructs no model, and performs no load, inference, activation, transition, or resident replacement.

The invariants are exact:

- resident cognitive serving != activation;
- resident cognitive serving != inference;
- resident cognitive serving != production chat serving;
- resident cognitive serving != model transition;
- current activation selects the eligible resident cognitive model;
- serving binds exact loaded cognition;
- `LOCAL_MODEL_INFERENCE` authorizes each cognitive effect;
- activation change invalidates the resident cognitive serving lifetime.

```text
commissioned != activated != resident-served != inference-admitted
             != developmentally interpreted != retained != truth
```

## Future architecture and custody

A later runtime may consume the authenticated canonical selection at `local-model/activation/active.json`, its exact activation receipt, authoritative catalog proof, hardened commissioning receipt, artifact bytes, and runtime identity. It may then obtain separate exact `MODEL_SERVING` admission, load only that model into a bounded resident lifetime, observe the loaded identity, bind a serving-backed governed invocation to `ResidentDevelopmentalCognitionOwner`, invalidate/unload on activation change, expose read-only health, and retain a durable receipt. It must not create a competing “resident active model” truth.

Every cognition call still requires separate exact `LOCAL_MODEL_INFERENCE` admission. The serving layer itself grants no inference. Production-chat serving is a separate consumer and lifetime, even when both consumers bind the same activation; resident cognition must not steal its worker, use chat health as resident authority, or mutate chat custody.

## Explicit enablement and fail-closed behavior

Legacy/default mode may retain the existing `LocalModel.autoload()` path until the new mode is explicitly adopted. Once an operator explicitly enables hardened resident cognitive serving, inability to authenticate current activation or establish exact serving must degrade or fail closed. It must never silently fall back to a configured `LocalModel` candidate. Configured startup composition is eligible; implicit or unconfigured boot/startup model selection is forbidden.

Today `sentientosd.py` directly calls `LocalModel.autoload()`, wraps that model in `GovernedLocalModelInvoker`, and supplies it to `ResidentDevelopmentalCognitionOwner`. Consequently, changing canonical production activation does not prove that the running resident developmental cognition model changed. The future bridge must deliberately close this gap.

Only after that runtime exists can the sequence `activation A -> resident serving A -> quiesce -> activation B -> resident serving B` constitute a resident cognitive-organ transition rather than only a production-chat transition. Transition authority and its A/B/A experiment remain separate.

## Approval and non-authority boundary

The definition requires explicit operator configuration, exact authenticated current activation and receipt, current catalog provenance, exact hardened commissioning and artifact/runtime identity, separate per-load `MODEL_SERVING` admission, separate per-call `LOCAL_MODEL_INFERENCE` admission, preservation of canonical activation and production chat serving, activation-change invalidation, fail-closed establishment, no enabled-mode legacy fallback, durable receipts, and read-only health. Definition registration satisfies none of those later runtime requirements.

The registration is digest-bound to its exact capability, definition, task, and repository-operator identity. Changed definition or approval evidence fails closed. Its posture is `definition_only` / `implementation_deferred`: definition != serving, model load, inference, activation, model transition, or resident model replacement.
