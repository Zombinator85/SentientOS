# Host Embodiment Reviewer Demo Trace

This doc follows the [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md). The reviewer demo trace is a deterministic, non-mutating proof artifact for seeing the full host embodiment ladder breathe without moving the body.

## Boundary

The demo trace is reviewer proof only. It is metadata-only export/proof, not live authorization, not real fulfillment, not real effect, not host mutation, not direct fan/PWM control, not thermal actuation, not power profile mutation, not process killing, not service restart, not package or driver installation, not file cleanup or deletion, not network egress, not provider invocation, not prompt assembly/export, not federation transport/sync/adoption, and not remote execution.

The default demo uses fake/sample thermal+PWM telemetry. It does not perform live host collection by default. PWM presence is shown as a signal, not control authority.

## What the demo proves

The trace exports the non-mutating ladder:

collector results → inventory → telemetry → pressure → policy → proposal → broker eligibility → broker review → fulfillment rehearsal → execution proof → authorization review → future authorization schema → controlled authorization contract → schema-only grant record → schema-only revocation record → metadata-only ledger → reviewer trace.

Reviewers should inspect that:

- PWM presence is not control authority.
- The controlled authorization contract is not a live grant.
- Grant/revocation records are schema-only/future-use-only.
- The ledger is metadata-only.
- Real actuation remains deferred.
- No fan/PWM/thermal/power/service/cleanup actions occur.
- No live authorization, no effect, and no host mutation occur.
- No network, provider, prompt, federation, or remote execution path is exercised.

## How to run

From the repository root:

```bash
python scripts/build_host_embodiment_trace.py --format json
python scripts/build_host_embodiment_trace.py --format markdown
python scripts/build_host_embodiment_trace.py --validate-only
python scripts/build_host_embodiment_trace.py --format json --output /tmp/sentientos-host-embodiment-trace.json
```

## Expected outputs

`--format json` emits the full deterministic trace payload with sorted keys. `--format markdown` emits a concise reviewer-readable summary. `--validate-only` exits successfully when the generated trace remains proof-only and prints no artifact. `--output PATH` writes only the explicit caller-supplied artifact path.

The golden fixture for the built-in thermal+PWM demo is `tests/fixtures/host_embodiment_trace_thermal_pwm_demo.json`. It contains no secrets, no real host identifiers, no prompt text, and no provider/network endpoint.

## Implementation links

- Export helpers: `sentientos/host_embodiment_trace_export.py`
- Demo CLI: `scripts/build_host_embodiment_trace.py`
- Trace builder: `sentientos/host_embodiment_trace.py`
- Tests: `tests/test_host_embodiment_trace_export.py`, `tests/test_build_host_embodiment_trace_script.py`
