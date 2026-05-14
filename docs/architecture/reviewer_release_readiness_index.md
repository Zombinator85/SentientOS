# Reviewer Release-Readiness Proof Index

## What this index is

This is a reviewer-facing map of the currently implemented proof surfaces for the
recent SentientOS hardening and federation-improvement work. It is meant to help
a technical reviewer move from the public overview to concrete tests, scripts,
and custody artifacts without reconstructing context from scattered PRs.

This index is not a release announcement, not a production-readiness claim, and
not a promise of provider invocation, federation transport, automatic adoption,
remote execution, or merge/apply/install behavior.

For the broader user-space operating-substrate trajectory and the concrete
missing subsystems still required, see
`docs/architecture/sentientos_trajectory_and_missing_organs.md`.

## Current implemented proof surfaces

### Control plane / authority admission

`tests/test_control_plane_kernel.py` covers explicit authority admission,
admission status visibility, and bounded process-local TTL idempotency. The
current posture is explicit admission, not implicit runtime authority.

### Maintenance degradation / fail-stop behavior

`tests/test_sentientosd_runtime_closure.py` covers runtime closure behavior,
maintenance forge/merge admission gating, and structured degradation when a
maintenance tick fails. Denied maintenance admission does not run forge or merge
ticks.

### Federation trust ledger recovery

`tests/test_trust_ledger.py` and `sentientos/tests/test_trust_ledger_recovery.py`
cover trust ledger state loading, event replay fallback, and degraded handling
for malformed state/events. Current recovery is startup recovery from local state
or local events, not a cross-process mutation-locking guarantee.

### Federation probe prioritization

`tests/test_trust_ledger.py` covers deterministic prioritization of suspicious
federation peers for probing. This is prioritization evidence only; it does not
create transport, sync, or enforcement authority by itself.

### Chat/model loading safety

`tests/test_chat_service_lazy_loading.py`, `tests/test_local_model.py`, and
`tests/integration/test_chat_mistral_runtime.py` cover lazy chat model loading and
local transformer loading defaults. Importing chat service code does not load the
model, and local custom model code execution defaults to `trust_remote_code=False`
unless explicitly opted in.

### Test runner bootstrap reliability

`tests/test_run_tests_bootstrap_airlock.py` and
`tests/test_integration_conftest_compat.py` cover the focused test-airlock path
and integration marker compatibility. The focused proof suites should not require
a broad runtime dependency install before collection.

### Docs build reliability

`tests/test_build_docs_tooling.py`, `python scripts/build_docs.py --check-deps`,
and `python scripts/build_docs.py` cover explicit docs dependency declaration and
building through the repository docs wrapper.

### Provider invocation denial custody Phase 100-103

The Phase 100-103 custody chain is metadata-only and release-blocking for real
provider invocation:

- `docs/architecture/phase100_provider_invocation_denial_closure_execplan.md`
- `docs/architecture/phase101_provider_invocation_denial_enforcement_snapshot_execplan.md`
- `docs/architecture/phase102_provider_invocation_denial_drift_review_execplan.md`
- `docs/architecture/phase103_provider_invocation_denial_custody_checkpoint_execplan.md`
- `tests/test_phase100_provider_invocation_denial_closure.py`
- `tests/test_phase101_provider_invocation_denial_enforcement.py`
- `tests/test_phase102_provider_invocation_denial_drift_review.py`
- `tests/test_phase103_provider_invocation_denial_custody_checkpoint.py`

These artifacts prove denial custody and drift review; they do not invoke a
provider, assemble a prompt, export prompt text, construct provider clients, or
open network/runtime authority.

### Federated improvement custody runway

The current implemented modules and tests are:

- `sentientos/federation/improvement_candidate.py` / `tests/test_federated_improvement_candidate.py`
- `sentientos/federation/improvement_intake_receipt.py` / `tests/test_federated_improvement_intake_receipt.py`
- `sentientos/federation/improvement_custody_runway.py` / `tests/test_federated_improvement_custody_runway.py`
- `sentientos/federation/improvement_local_variant_artifact.py` / `tests/test_federated_improvement_local_variant_artifact.py`
- `sentientos/federation/improvement_lineage_comparison_receipt.py` / `tests/test_federated_improvement_lineage_comparison_receipt.py`
- `sentientos/federation/improvement_dissemination_receipt.py` / `tests/test_federated_improvement_dissemination_receipt.py`

These receipts and artifacts are custody/evidence/readiness surfaces only. They
do not transport, sync, adopt, execute, merge, apply, install, force updates, or
expand runtime authority.

## Hard invariants currently proven

- Authority is explicit and admitted.
- Denied maintenance does not execute forge/merge ticks.
- Maintenance failure emits one structured degradation signal.
- Admission idempotency is bounded process-local TTL, not pretend-durable.
- Trust ledger recovers from state or events and degrades on malformed input.
- Suspicious federation peers are prioritized deterministically.
- Chat service import does not load the model.
- Local model custom code execution defaults false.
- Focused tests do not require broad runtime dependency install.
- Docs build dependencies are explicit.
- Provider invocation remains release-blocked.
- Federated improvement receipts do not transport, adopt, execute, merge, apply,
  install, or force updates.

## Proof commands

Run from the repository root. Expected posture for each command is successful
completion unless the local environment is missing an explicitly declared docs or
test dependency, in which case the failure should be treated as a bootstrap issue
and fixed through the documented wrapper path.

```bash
# Test-runner bootstrap and docs tooling smoke coverage.
python -m scripts.run_tests -q tests/test_run_tests_bootstrap_airlock.py tests/test_build_docs_tooling.py

# Control-plane admission and runtime closure / maintenance gating.
python -m scripts.run_tests -q tests/test_control_plane_kernel.py tests/test_sentientosd_runtime_closure.py

# Federation trust ledger recovery and probe prioritization.
python -m scripts.run_tests -q tests/test_trust_ledger.py sentientos/tests/test_trust_ledger_recovery.py

# Chat/model lazy loading and local model safety.
python -m scripts.run_tests -q tests/test_chat_service_lazy_loading.py tests/test_local_model.py tests/integration/test_chat_mistral_runtime.py

# Integration marker compatibility.
python -m scripts.run_tests -q tests/test_integration_conftest_compat.py

# Federated improvement custody/evidence runway.
python -m scripts.run_tests -q tests/test_federated_improvement_candidate.py tests/test_federated_improvement_intake_receipt.py tests/test_federated_improvement_custody_runway.py tests/test_federated_improvement_local_variant_artifact.py tests/test_federated_improvement_lineage_comparison_receipt.py tests/test_federated_improvement_dissemination_receipt.py

# Context hygiene / prompt-boundary verification.
python scripts/verify_context_hygiene_prompt_boundaries.py

# Audit chain verification.
python scripts/verify_audits.py --strict

# Immutable manifest verification.
python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json

# Docs dependency check and docs build.
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```

## Deferred / explicitly not implemented

- Real provider invocation.
- Prompt assembly or prompt-text export for provider invocation.
- Federation transport/sync for improvement receipts.
- Automatic adoption.
- Remote execution.
- Merge/conflict-resolution engine.
- Apply/install/update engine for federated improvement receipts.
- Production execution from rehearsal/readiness receipts.
- Durable cross-process admission idempotency.
- Cross-process trust ledger mutation locking.

## How to review

1. Read `docs/architecture/public_technical_overview.md` first.
2. Run the proof-map commands above from the repository root.
3. Inspect `tests/test_control_plane_kernel.py` and `tests/test_sentientosd_runtime_closure.py`.
4. Inspect `tests/test_trust_ledger.py` and `sentientos/tests/test_trust_ledger_recovery.py`.
5. Inspect `tests/test_chat_service_lazy_loading.py`, `tests/test_local_model.py`, and `tests/integration/test_chat_mistral_runtime.py`.
6. Inspect the federated improvement receipt tests listed in the custody runway section.
7. Build docs with `python scripts/build_docs.py --check-deps` and `python scripts/build_docs.py`.
