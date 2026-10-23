# Sequence 628 — reject unknown Federation Health timestamp offsets

Sequence 628 prevents Federation Health from treating RFC 3339's `-00:00` timestamp marker as UTC. That marker states that the local offset is unknown; Python's `datetime.fromisoformat` otherwise normalizes it to a zero offset and can incorrectly count the event as recent. The reader now skips its timestamp for freshness calculations. It preserves the peer row's existing node-count behavior and continues to interpret the repository logger's legacy naive timestamps as UTC.

The new no-legacy-skip regression is bound into the Federation Health source-validation task-acceptance manifest. The snapshot schema, configured-local-log source label, and `live_telemetry: false` remain unchanged. This adds no remote telemetry, peer-claim trust, admission, planning, execution, or decision authority.

PR #2712 candidate `90e0ec864960a4b4534f6dde1a2378779ae36caf` (tree `3faa102f92bad5d542c39a7aeaf397e430005b8b`) merged normally into main as `36458e4c5e3724f1e642b53ca4160cf24eb7ab4b` (tree `3faa102f92bad5d542c39a7aeaf397e430005b8b`), with first parent `769bcc2201a2b42eb793ab378b3567e1dde9075c`. Exact-candidate verification and post-merge verification passed.

## Exact-candidate verification

Required Quality Gate #39990260982 passed strict hosted Administrator audits, exact acceptance, the landing finalizer, and the separate pre-publication metadata guard. CI #39991023817 passed source validation including `test_compute_health_does_not_treat_unknown_timestamp_offset_as_utc`, the integrated resource-to-cognition lifecycle, canonical planning separation, Federation relay/replay controls, transition/campaign regressions, Mypy/pytest, documentation linkcheck, and Helm/Kubernetes. The same-SHA push CI #39991017967 also passed. Invariants #39991023756, CPU smoke #39991023806, lint #39991023800, build #39991023734, validation #39991023822, and gradient #39991023811 passed.

## Post-merge source verification and Health execution

On exact source main `36458e4c5e3724f1e642b53ca4160cf24eb7ab4b`, Required Quality Gate #39990963499, CI #39990963274, Invariants #39990962917, Docker Image #39990963150, CPU smoke #39990963208, deployment #39990963068, and the main-branch Health workflow #39990963059 passed. CI completed source validation including the unknown-offset regression, the integrated lifecycle, Mypy/pytest, docs linkcheck, and Helm/Kubernetes. Nightly Self Check #39990963171 passed. Forge Smoke #39990963154 was skipped by its workflow conditions.

Federation Health run #39990963059 executed against `36458e4c5e3724f1e642b53ca4160cf24eb7ab4b` with event `push`. Hosted Administrator availability, report generation, and run-receipt binding passed. It truthfully reports one configured node, zero events in the last 24 hours, and a stale configured local snapshot with latest event `2025-06-05T16:25:13.805813Z`; this is not live federation telemetry.

The GitHub App publisher created PR #2713 containing only `docs/FEDERATION_HEALTH_EXECUTION.json`. Its receipt binds run #39990963059 and source SHA `36458e4c5e3724f1e642b53ca4160cf24eb7ab4b`, records successful Administrator preflight and report digest `e6a98f8e9d89cc626eb6a329fb9c0c26d289f8de6200db37a577044ca793959c`, and merged normally as `cc2d98665a191c31ef0e0ccddccbe422ed18d267`. PR #2713's exact-candidate checks, privileged finalizer, and separate metadata guard passed.

This segment follows `segment-sha256:e24bc43344ec3f921bcaeac82ec17771a1a2814b27f7c4e0a5707c214d363b16`.
