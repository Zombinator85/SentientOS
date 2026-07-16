# Host Resource Observation Runtime

`sentientos.host_resource_runtime` closes the read-only host telemetry loop by composing the existing safe host collectors, host resource telemetry snapshot, pressure governor, and proposal-only policy receipts into one admitted maintenance-cycle runtime.

## Authority and admission

Each production cycle requests `AuthorityClass.OBSERVATION` admission from the control-plane kernel. Non-allow outcomes return without invoking collectors, and the coordinator caches the correlation ID so a duplicate maintenance tick cannot run a second collector epoch.

Observation admission is not execution authority. The runtime records `no_effect_authority`, `host_mutation_performed=false`, and `repository_mutation_performed=false`; fan/PWM writes, process control, service restart, package/driver installation, provider invocation, prompt assembly, privilege execution, and resource actuation remain blocked or deferred.

## Bounded collector epoch

The deterministic plan contains the current collectors from `sentientos.host_collectors` in stable order. The budget sets maximum collector count, per-collector timeout, total deadline, bounded workers, and zero retries by default. Exceptions and timeouts are represented as contained telemetry results; late timed-out results are excluded from semantic identity and the sealed epoch.

Required collectors distinguish stale or unavailable telemetry from zero values. Optional unsupported platform collectors are recorded truthfully as unavailable rather than failed host effects.

## Validation, redaction, and identity

Runtime validation checks collector IDs, statuses, serialized size, finite numbers, telemetry-only fields, false-effect fields, nested content, pressure reports, policy decisions, and proposal receipts. Durable artifacts redact hardware addresses, paths, usernames, command lines, environment/credential-looking values, tracebacks, PIDs, and arbitrary file content. Semantic identity ignores timestamps, durations, worker order, roots, PIDs, and artifact locations while binding collector semantics, snapshot posture, pressure labels, policy decision, and receipt IDs.

## Artifacts, World-State, and dashboard

Each admitted cycle atomically persists plan, admission reference, normalized collector results, epoch, resource snapshot, pressure report, policy decision, proposal receipts, compact summary, and deterministic Markdown below the injected external runtime-state root. `sentientosd` passes the exact in-memory evaluation from the maintenance tick into the terminal World-State Board build, so dashboard and board rendering never rerun collectors. The dashboard exposes an authenticated read-only `/api/world-state/host-resource` projection with admission, freshness/status counts, unavailable/invalid collectors, pressure labels, policy posture, proposal receipt IDs, and explicit no-effect posture.
