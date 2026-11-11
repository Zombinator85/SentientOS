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

## Runtime composition and custody

The separately implemented `resident_cognitive_model_serving` runtime consumes the authenticated canonical selection at `local-model/activation/active.json`, verifies its exact activation receipt, catalog proof, hardened commissioning receipt, artifact bytes, and runtime identity, then obtains separate exact `MODEL_SERVING` admission. It loads and observes only that activation in a bounded resident lifetime, binds a serving-backed governed invocation to `ResidentDevelopmentalCognitionOwner`, invalidates and unloads on activation change, exposes read-only health, and retains durable serving and invalidation receipts. It does not create a competing “resident active model” truth.

Every cognition call still requires separate exact `LOCAL_MODEL_INFERENCE` admission. Serving itself grants no inference. Production-chat serving is a separate consumer and lifetime, even when both consumers bind the same activation; resident cognition must not steal its worker, use chat health as resident authority, or mutate chat custody.

## Explicit enablement and fail-closed behavior

Absent or disabled resident-serving configuration preserves the legacy resident path. Once an operator explicitly enables hardened resident cognitive serving, inability to authenticate current activation or establish exact serving degrades or fails closed for resident cognition. It does not silently fall back to a configured `LocalModel` candidate. Configured startup composition is eligible; implicit or unconfigured boot/startup model selection is forbidden.

`sentientosd.py` now composes the exact activated model through the resident-serving controller when the explicit configuration is enabled; the daemon can still use its legacy `LocalModel.autoload()` path when that mode is absent. The explicit mode closes the model-selection gap in source composition. A source composition does not prove a qualifying production model transition or cognitive benefit.

The bounded live transition path can coordinate `activation A -> resident serving A -> quiesce -> activation B -> resident serving B` under separate transition approval and exact stage admission. This is distinct from production-chat serving. The runtime and transition machinery are implemented, but repeated real production transition evidence and measured longitudinal benefit remain outstanding.

## Approval and non-authority boundary

The definition requires explicit operator configuration, exact authenticated current activation and receipt, current catalog provenance, exact hardened commissioning and artifact/runtime identity, separate per-load `MODEL_SERVING` admission, separate per-call `LOCAL_MODEL_INFERENCE` admission, preservation of canonical activation and production chat serving, activation-change invalidation, fail-closed establishment, no enabled-mode legacy fallback, durable receipts, and read-only health. The runtime implements these bounded serving requirements when explicitly configured; the governance registration itself satisfies none of them.

The registration is digest-bound to its exact capability, definition, task, and repository-operator identity. Changed definition or approval evidence fails closed. Its posture remains `definition_only`: registration is not serving, model load, inference, activation, model transition, or resident model replacement.
