# Resident cognitive model serving

The `resident_cognitive_model_serving` runtime is an explicit, operator-enabled bridge from resident developmental cognition to the authenticated current hardened activation. Its configuration schema is `sentientos.resident_cognitive_model_serving_config:v1`; it accepts only an installation identity, a non-placeholder serving operation identity, and the exact expected activation-state digest. It never selects a model, artifact, runtime, executable, or fallback.

The controller admits `establish_exact_resident_cognitive_model_serving` as `MODEL_SERVING` for principal `deterministic_resident_cognitive_model_serving_controller`, then loads and observes the exact activated worker. Serving evidence uses `sentientos.resident_cognitive_model_serving_receipt:v1` and `sentientos.resident_cognitive_model_serving_invalidation:v1` below `local-model/resident-cognitive-serving/`; production-chat custody remains under `local-model/serving/`.

The opaque adapter composes ordinary governed requests. Each actual cognition therefore requires a separate `LOCAL_MODEL_INFERENCE` admission, with pre- and post-generation currentness checks. Establishment performs no inference. Activation, receipt, catalog, worker-liveness, or loaded-identity drift invalidates and unloads the lifetime; it does not load the successor activation and does not fall back to `LocalModel.autoload()`.

Absent or disabled configuration preserves the legacy resident path. Enabled configuration fails closed for resident cognition while the general invoker remains available to unrelated consumers such as Genesis advice. Health schema `sentientos.resident_cognitive_model_serving_health:v1` is read-only and never establishes serving or performs inference.

This bounded runtime does not grant resident cognitive-model transition authority, automatic rebind, autonomous switching, model acquisition, commissioning, activation mutation, production-chat mutation, provider/network/tool/host authority, or identity and learning conclusions.
