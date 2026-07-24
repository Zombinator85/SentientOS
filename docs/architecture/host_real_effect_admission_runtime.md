# Host Real Effect Admission Runtime

The host real effect admission runtime consumes an exact persisted `host_dry_run_audit_closure_runtime.v2` bundle and records metadata-only implementation-planning admission evidence. It validates the source through `validate_persisted_closure_bundle()` before calling the real-effect admission builders, so legacy, loose, incomplete, blocked, contradicted, tampered, or partially reconstructed closure evidence is rejected before admission policy is evaluated.

## Persisted custody

Each admitted runtime request persists a replay-safe bundle containing the runtime request, runtime plan, exact source closure reference, embedded source `DryRunClosureBundle` semantic record, candidate, admission decision, plan scaffold or block receipt, `RealEffectAdmissionBundle`, validation findings, runtime receipt, content manifest, final manifest, deterministic JSON summary, Markdown summary, `latest.json`, and `replay_index.json`.

Replay is independent of the original closure path. Once the admission bundle is persisted, an identical request with the same correlation ID replays from the stored admission bundle and performs zero admission-builder calls, even if the original source closure directory has been removed. Reusing the same correlation ID for different semantic input is rejected as a conflict.

## Policy outcomes

Diagnostics, operator-review, and resource-pressure domains may be eligible for implementation planning. Thermal safety remains conditional. Cooling, power, service, and cleanup domains remain blocked by default.

## Authority boundary

This runtime is metadata-only. It does not start implementation, authorize execution, load or invoke a backend, fulfill host actions, perform real effects, mutate host state, call a control plane, invoke providers, run subprocesses, or call the local diagnostic effect pilot. The persisted request, plan, candidate, decision, plan scaffold or block receipt, admission bundle, validation findings, receipt, manifests, and summaries keep implementation/execution/effect flags false.

## CLI

`scripts/build_host_real_effect_admission_runtime.py` provides:

- `evaluate --closure-bundle-root --output-root` to validate a strict-v2 source and persist admission runtime evidence.
- `validate-source --closure-bundle-root` to read-only validate a persisted source closure bundle.
- `validate-bundle --bundle` or `--output-root` to read-only validate a persisted admission bundle.
- `latest-summary --output-root` to read the latest validated summary.

Validation commands are read-only and exit nonzero when evidence is invalid.
