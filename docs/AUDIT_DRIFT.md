# Audit Drift Detection and Baseline Lifecycle

This document defines how SentientOS captures audit baselines and how drift is detected in CI.

## Drift Signals

`detect_audit_drift` compares a live audit snapshot against a captured baseline using two independent signals:

- **Tuple drift**: changes in canonical issue tuples (`code`, `path`, `expected`, `actual`).
- **Fingerprint drift**: changes in the manifest fingerprint (`baseline_fingerprint` vs `current_fingerprint`).

A run is marked `drifted: true` when either signal changes.

### Drift Classification

The drift report includes:

- `tuple_diff_detected: bool`
- `fingerprint_changed: bool`
- `drift_type: "none" | "tuple_only" | "fingerprint_only" | "tuple_and_fingerprint"`
- `drift_explanation: str`

Interpretation:

- `none`: no tuple or fingerprint changes.
- `tuple_only`: issue tuples changed while fingerprint comparison is unchanged.
- `fingerprint_only`: manifest changed while issue tuples stayed the same.
- `tuple_and_fingerprint`: both changed.

## Baseline Lifecycle

## Common Operations

Use the ergonomic Make targets for day-to-day baseline lifecycle operations:

- `make audit-baseline` captures `glow/audits/baseline/audit_baseline.json`.
- `make audit-baseline ACCEPT_MANUAL=1` passes `--accept-manual` for explicit manual-issue acceptance.
- `make audit-drift` runs drift detection and prints `drift_type` and `drift_explanation`.
- `make audit-verify` runs `python -m scripts.audit_immutability_verifier`.


Baselines are captured with `capture_audit_baseline` and written to:

- `glow/audits/baseline/audit_baseline.json`

A baseline now records provenance metadata:

- `captured_at`: UTC ISO-8601 timestamp.
- `captured_by`: git commit SHA when available.
- `tool_version`: capture tool version identifier.

`timestamp` remains in the payload for compatibility. Baselines are serialized deterministically (`sort_keys=True`) and manifest fingerprinting is computed from manifest content only, so timestamps do not influence fingerprint values.

## When to Regenerate Baseline

Regenerate the baseline when you intentionally accept audit-state changes, including:

- expected new or resolved audit issues,
- expected log-manifest changes that should be treated as accepted state,
- intentional operational changes in tracked audit logs.

Do **not** regenerate baseline for unexplained drift. Investigate first.

## Manual Issue Acceptance (`--accept-manual`)

`make audit-baseline ACCEPT_MANUAL=1` is equivalent to invoking `capture_audit_baseline --accept-manual`.

By default, baseline capture refuses unclean audits.

Use `--accept-manual` only when:

1. audits are unclean,
2. remaining issues are explicitly manual-required,
3. you are intentionally recording acceptance.

This sets `manual_issues_accepted: true` and stores the manual-required issue inventory for later drift accounting.

## CI Strict Mode

When `SENTIENTOS_CI_FAIL_ON_AUDIT_DRIFT=1`, CI fails for any `drift_type != "none"`.

The drift tool emits a failure log line describing the drift class and triggering component (`tuple_diff_detected`, `fingerprint_changed`, or `tuple_and_fingerprint`).
