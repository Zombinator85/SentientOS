# Explicit local-model chat recovery authority

## Status and motivation

`local_model_chat_recovery` is a metadata-only, eligibility-only task-authority
contract for a future recovery implementation. It admits planning of one explicit,
operator-approved recovery of a failed hardened production serving lifetime. It does
not restart a process, load a model, establish serving, perform inference, issue an
approval, or grant runtime authority. Effectful recovery remains deferred.

The contract preserves the operator's decision at the failure boundary. An eligible
serving or process failure stays failed and visible: automatic supervisor restart
remains disabled, and `local_model_chat` retains `restart_policy="never"`.

## Exact eligible lifecycle and preconditions

The future controller may consider recovery only when all of the following facts can
be bound and verified:

1. The canonical runtime explicitly enabled the `local_model_chat` service.
2. The prior service lifetime began with authenticated installation identity, its
   exact startup configuration, and an explicit `prior_serving_operation_id`.
3. That exact lifetime is unhealthy due to an eligible serving/process failure.
4. Automatic restart remains disabled.
5. An operator explicitly requests recovery and supplies a non-placeholder,
   non-wildcard `replacement_serving_operation_id`.
6. One recovery intent binds the exact runtime/supervisor generation (or equivalent
   runtime identity), exact service id `local_model_chat`, exact prior startup
   configuration, exact prior serving lifetime evidence, exact expected activation
   provenance, exact fresh serving-operation identity, and exact recovery correlation
   identity.
7. Genuine external operator approval evidence is bound to that exact intent.
8. Authoritative current hardened activation provenance is unchanged from the
   provenance bound to the prior lifetime and recovery intent.
9. Both `prior_serving_operation_id` and `replacement_serving_operation_id` are bound,
   and verification proves they differ.

If activation provenance changed, recovery is not eligible. Switching or adopting
the new activation requires a distinct explicit lifecycle action outside this
capability. Recovery never provides hot activation switching.

## Authority separation

After verifying every precondition, the future deterministic controller must request
the existing `AuthorityClass.DAEMON_RESTART` with
`action_kind="restart_daemon"` and exactly
`target_subsystem="local_model_chat"`. Only an `ALLOW` decision can permit the bounded
restart of that exact supervised child. The restart uses the already-fixed hardened
launcher custody and the newly approved operation identity. This capability creates
no new runtime `AuthorityClass` and does not alter `DAEMON_RESTART`.

The replacement child then independently opens authenticated installation custody and
calls the existing `ProductionServingController.establish(...)`. It must independently
obtain `MODEL_SERVING`; neither eligibility, operator approval, nor `DAEMON_RESTART`
grants serving. The existing serving controller remains authoritative for validation
of the replacement operation identity. Recovery succeeds only after semantic
serving-current readiness is observed.

Recovery performs zero inference. `MODEL_SERVING` does not grant
`LOCAL_MODEL_INFERENCE`, and each later generation must independently obtain
`LOCAL_MODEL_INFERENCE`. The required chain is therefore:

```text
explicit operator recovery approval
    -> DAEMON_RESTART
    -> replacement child starts
    -> independent MODEL_SERVING
    -> semantic serving-current readiness

each later generation -> independent LOCAL_MODEL_INFERENCE
```

## Failure and denial

Missing, ambiguous, stale, mismatched, reused, placeholder, or wildcard evidence
fails closed. A denied restart admission produces no restart. A replacement child
that cannot obtain its own serving admission does not become ready. Readiness itself
never grants recovery or inference authority, and no simulation or provider fallback
may disguise failure.

Automatic recovery, automatic restart, an effectful recovery controller, approval
issuance, recovery-intent execution, child-restart execution, serving
re-establishment, hot activation switching, and universal/one-click deployment are
all deferred to separately governed work.
