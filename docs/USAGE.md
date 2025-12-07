# SentientOS Usage Guide

This guide describes how to exercise the unified SentientOS orchestrator and
CLI. All entry points are deterministic, approval-gated where appropriate, and
avoid persistence unless an explicit approval flag is provided.

## SentientOrchestrator overview

The `SentientOrchestrator` class exposes a stable API surface across the
consciousness cycle, SSA agent, PDF prefill, and review bundle helpers.

```python
from sentientos.orchestrator import SentientOrchestrator

orchestrator = SentientOrchestrator(profile=my_profile, approval=True)
cycle_report = orchestrator.run_consciousness_cycle()
```

## Running a consciousness cycle

`run_consciousness_cycle()` executes a deterministic, side-effect-free cycle
for debugging and introspection. It never schedules work or persists state.

```python
payload = orchestrator.run_consciousness_cycle()
```

## Preparing an SSA profile

SSA operations expect a JSON profile that matches the schema in
`agents/forms/schemas/ssa_claim_profile.schema.json`. Profiles are passed to
`SentientOrchestrator(profile=...)` and remain in-memory only.

## SSA workflows

All SSA routines are available from the orchestrator and gated by the
`approval` flag supplied at construction time.

- **Dry-run**: build deterministic browser and screenshot plans.
  ```python
  orchestrator = SentientOrchestrator(profile=profile)
  plan = orchestrator.ssa_dry_run()
  ```
- **Execute**: drive an OracleRelay session. Requires `approval=True`.
  ```python
  orchestrator = SentientOrchestrator(profile=profile, approval=True)
  result = orchestrator.ssa_execute(relay)
  ```
- **Prefill SSA-827**: generate a redacted PDF preview and bytes. Requires
  `approval=True`.
  ```python
  orchestrator = SentientOrchestrator(profile=profile, approval=True)
  bundle = orchestrator.ssa_prefill_827()
  ```
- **Review bundle**: assemble and optionally export a redacted archive.
  ```python
  bundle = orchestrator.ssa_review_bundle(execution_result, pdf_bytes)
  archive = orchestrator.export_review_bundle(bundle)
  ```

## Approval gating

Privileged operations (SSA execution, PDF creation, bundle export) are blocked
unless `approval=True` is provided when constructing the orchestrator. When the
approval flag is absent these methods return `{ "status": "approval_required" }`
or `{ "error": "no_profile_loaded" }` without performing any side effects.

## Redaction behavior

Review bundles and CLI summaries redact selectors, values, and bytes by
default. Redacted previews are deterministic and safe to log. No persistence
occurs unless an approval flag is explicitly provided during bundle export or
file saves.

## CLI quickstart

Run the CLI via `python -m cli.sentientos_cli` or by adding it as an entry
point in your environment.

```
sentientos cycle
sentientos ssa dry-run --profile ./profile.json
sentientos ssa execute --profile ./profile.json --approve
sentientos ssa prefill-827 --profile ./profile.json --approve
sentientos ssa review --bundle ./bundle.json
sentientos integrity
sentientos version
```

All CLI commands print JSON payloads. Approval-gated commands require the
`--approve` flag; otherwise they return a deterministic `approval_required`
message without performing privileged actions.
