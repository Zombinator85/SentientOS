# GitHub-hosted acceptance

This developer-workflow boundary applies the repository's canonical validation and landing contracts to untrusted hosted candidates. A green envelope is insufficient unless pytest actually loaded the reporter, completed collection, selected and collected positive counts, reached at least one call phase, emitted complete metrics and provenance, passed every exact required node, and bound that evidence to the candidate SHA.

## Effect and authorization boundaries

Importing `scripts.lock` or `api.actuator` is inspection, not authority. Imports must not authorize, prompt, create runtime directories, execute plugins, start threads, invoke processes, or perform external effects. Lock `freeze` and `install`, actuator shell/HTTP/file/email/webhook/workflow/talkback operations, asynchronous execution, and memory-backed action execution authorize immediately before their protected effects. External actuator plugin loading is unsupported. Read-only lock checking and builtin actuator metadata inspection remain unprivileged.

## Validation and integrity

Canonical completion statuses are `bootstrap_failed`, `collection_failed`, `zero_tests_collected`, `zero_call_phase_outcomes`, `metrics_missing`, `validation_failed`, and `validation_complete`. Only `validation_complete` is hosted acceptance evidence; collection-only diagnostics are never complete. Provenance chain integrity answers whether artifacts are intact, while validation sufficiency answers whether tests ran. The overall analyzer states are `OK`, `ALERT`, `INSUFFICIENT_EVIDENCE`, and `INTEGRITY_BROKEN`; an intact empty or incomplete chain is insufficient, never OK.

The **Required Quality Gate** workflow exposes the unique check **Required / Quality Gate** on Ubuntu 24.04 with Python 3.11 and read-only contents permission. It installs SentientOS, runs `pip check`, verifies inert imports, executes the nineteen exact acceptance nodes through `scripts.run_tests`, verifies a runtime v1 acceptance manifest, validates completion counts and SHA binding, runs strict trend analysis, and always uploads provenance, acceptance result, trend report, and the pre-pytest import-smoke result. Missing, malformed, incomplete, zero-count, stale, or failed evidence fails the job.

Python package initializers are never authorization boundaries: importing a protected
subsystem is not itself a protected effect. Accordingly, `api/__init__.py` is
intentionally limited to inert package definition. Protected actuator effects retain
authorization immediately before execution. External actuator plugin loading is not
supported; configured Python files have no actuator execution authority. Log path resolution similarly only
selects a `Path`; the compatible creating helpers and actuator write boundaries create
parents when a runtime write actually requires them.

`scripts/verify_import_inertness.py` runs after minimal installation and `pip check`,
and before `scripts.run_tests`. It writes
`glow/test_runs/quality_gate_import_smoke.json` using
`sentientos.import_inertness:v1`, even on failure. Its bounded child-process evidence
classifies readiness, import failure, privilege invocation, filesystem mutation,
plugin execution, or verifier error. Every module receives a fresh interpreter and
fresh configured log, sandbox, plugin, and autonomous-log paths. The `api` imports
replace both privilege helpers with failing sentinels first, because root execution
could otherwise conceal an unauthorized import-time call. A harmless external plugin
provides an execution marker without granting plugin initialization authority.

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

## Privilege-inert pytest bootstrap

Pytest initialization is test infrastructure, not a privilege boundary. `tests/conftest.py`
must remain inert: import and collection do not authorize, align covenant state, prompt,
terminate, or write privilege-ledger/runtime policy state. Protected-operation tests invoke
or monkeypatch their own authorization boundary locally.

Import smoke proves ordinary package imports are effect-inert; the separate
`sentientos.pytest_bootstrap:v1` subprocess proof proves real pytest collection and one
harmless call phase with sentinels installed on the actual `sentientos.privilege`
functions. Its bounded artifact records repository SHA, Python version, exact node and
child command, return code/output tails, reporter and collection completion, collected
and call-phase counts, sentinel state, and a status (`pytest_bootstrap_ready`,
`privilege_invoked`, `bootstrap_failed`, `collection_failed`, `zero_tests_collected`,
`zero_call_phase_outcomes`, `metrics_missing`, or `verifier_error`). The required gate
orders minimal installation, `pip check`, import smoke, pytest-bootstrap proof, nineteen
exact call phases, acceptance binding, strict provenance analysis, then always-on evidence
upload.
