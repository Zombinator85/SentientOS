# GitHub-hosted acceptance

This developer-workflow boundary applies the repository's canonical validation and landing contracts to untrusted hosted candidates. A green envelope is insufficient unless pytest actually loaded the reporter, completed collection, selected and collected positive counts, reached at least one call phase, emitted complete metrics and provenance, passed every exact required node, and bound that evidence to the candidate SHA.

## Effect and authorization boundaries

Importing `scripts.lock` or `api.actuator` is inspection, not authority. Imports must not authorize, prompt, create runtime directories, execute plugins, start threads, invoke processes, or perform external effects. Lock `freeze` and `install`, actuator shell/HTTP/file/email/webhook/workflow/talkback operations, asynchronous execution, memory-backed action execution, and deliberate external-plugin loading authorize immediately before their protected effects. Read-only lock checking and builtin actuator metadata inspection remain unprivileged.

## Validation and integrity

Canonical completion statuses are `bootstrap_failed`, `collection_failed`, `zero_tests_collected`, `zero_call_phase_outcomes`, `metrics_missing`, `validation_failed`, and `validation_complete`. Only `validation_complete` is hosted acceptance evidence; collection-only diagnostics are never complete. Provenance chain integrity answers whether artifacts are intact, while validation sufficiency answers whether tests ran. The overall analyzer states are `OK`, `ALERT`, `INSUFFICIENT_EVIDENCE`, and `INTEGRITY_BROKEN`; an intact empty or incomplete chain is insufficient, never OK.

The **Required Quality Gate** workflow exposes the unique check **Required / Quality Gate** on Ubuntu 24.04 with Python 3.11 and read-only contents permission. It installs SentientOS, verifies inert imports, executes the exact acceptance nodes through `scripts.run_tests`, verifies a runtime v1 acceptance manifest, validates completion counts and SHA binding, runs strict trend analysis, and always uploads provenance, acceptance result, and trend report. Missing, malformed, incomplete, zero-count, stale, or failed evidence fails the job.

## Hosted platform posture

The Ubuntu development image installs Python packages only in `/opt/venv`; it does not bypass PEP 668. Disabled accelerator configurations are absent from the active matrix and therefore cannot check out or build. Pull requests use a release-validation job that installs and imports SentientOS, runs the publisher in no-op mode, and builds artifacts without secrets or publication steps. Protected version tags use the separately conditioned publication job.

## Operator checklist

Repository code does not prove remote settings are configured. After this change exists on GitHub, an operator should:

1. Require `Required / Quality Gate` on `main`.
2. Require branches to be current before merge.
3. Disable bypass or audit it tightly.
4. Optionally require one approval or a merge queue.
5. Enable automatic deletion of merged branches.

Do not claim branch protection, hosted success, or publication from local workflow contracts alone.
