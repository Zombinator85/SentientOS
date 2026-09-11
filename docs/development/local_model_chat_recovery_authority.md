# Explicit local-model chat recovery authority

## Implemented bounded runtime

`local_model_chat_recovery` now implements one explicit, externally approved recovery
transaction for an eligible failed canonical hardened-chat lifetime. The operator first
prepares a deterministic intent with `python -m sentientos.ops runtime
local-model-chat-recovery-intent`, obtains approval outside SentientOS, and publishes an
immutable request with `request-local-model-chat-recovery`. Publication performs no
restart, model load, or inference. The enabled running runtime alone consumes requests.

The controller re-verifies, under an installation-scoped lock, the exact supervisor
generation and failed state, runtime startup configuration, immutable prior serving
receipt, approval validity, unchanged hardened activation provenance, and that the
replacement serving-operation identity has never appeared in installation serving
custody. Every terminal request gets one immutable receipt and is never retried.

External approval evidence must carry timezone-aware ISO-8601 `not_before`,
`approved_at`, and `expires_at` values ordered as `not_before <= approved_at <=
expires_at`, and observation must be inside that window. Operator identity, evidence id,
source, and provenance must be explicit and non-placeholder. Production requires an
explicit `synthetic_test_evidence=false`; only the dedicated test seam may admit true
synthetic evidence. The semantic digest covers the complete approval body, and naive
timestamps fail closed.

## Mechanically separate authority

Immediately before the sole lifecycle effect the controller independently requests
existing `AuthorityClass.DAEMON_RESTART`, with `action_kind="restart_daemon"`, actor
`deterministic_local_model_chat_recovery_controller`, and target `local_model_chat`.
Only an exact `ALLOW` permits the fixed adapter to replace the process lifetime. The
controller neither obtains nor pre-grants `MODEL_SERVING`.

The replacement fixed launcher carries the approved fresh serving operation and exact
expected activation-state digest into `ProductionServingController.establish`. The child
independently obtains `MODEL_SERVING`; a changed activation fails before admission and
model load. Success requires bounded `/readyz` semantic `serving_current`, not process
liveness. Recovery performs zero inference and grants no `LOCAL_MODEL_INFERENCE`; every
later chat generation independently obtains that authority.

The successful path is tested as one effectful transaction through `process_request()`
and `process_pending()`, from evidence verification and exactly one `DAEMON_RESTART`
through replacement, `serving_current`, snapshot advancement, and a zero-inference
terminal receipt. Existing receipts are schema-, request-, installation-, and
semantic-digest-verified before replay.

## Preserved boundaries

`restart_policy="never"` remains intentional. Generic and automatic supervisor restart,
automatic recovery, hidden retries, approval issuance, hot activation switching,
recovery across changed activation, arbitrary process/model/path selection, platform
service installation, and one-click deployment remain deferred. A failed child launch,
serving establishment, or readiness observation is terminal and leaves the startup
snapshot bound to the prior lifetime.

The installation lock provides in-process concurrency and replay safety. Abrupt process
loss after restart but before terminal receipt publication is not deterministically
finalizable here; this implementation makes no crash-safe exactly-once or automatic-retry
claim.
