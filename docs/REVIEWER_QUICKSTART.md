# Reviewer's Quickstart

This one-page checklist gives reviewers a deterministic snapshot of audit and
federation posture using the current command surface.

1. Clone the repository and install dependencies (`bash setup_env.sh`).
2. Verify audit chains:
   ```bash
   verify_audits --strict
   ```
3. Check read-only runtime diagnostics:
   ```bash
   python -m sentientos doctor
   ```
4. Check fleet observability rollups:
   ```bash
   python -m sentientos.ops observatory fleet --json
   python -m sentientos.ops observatory artifacts --json
   ```
5. Check node and constitution posture:
   ```bash
   python -m sentientos.ops node health --json
   python -m sentientos.ops constitution verify --json
   ```
6. Check the repo-wide mypy baseline ratchet and the focused workspace typed surface:
   ```bash
   python scripts/check_mypy_baseline.py
   python -m mypy --follow-imports=skip --hide-error-context --no-color-output --show-column-numbers --show-error-codes sentientos/workspace_change_set_admission.py scripts/admit_workspace_change_set.py sentientos/workspace_change_set_preflight.py scripts/preflight_workspace_change_set.py sentientos/workspace_change_set_execution.py scripts/run_workspace_change_set_transaction.py sentientos/workspace_change_set_execution_verification.py scripts/verify_workspace_change_set_execution.py sentientos/workspace_change_set_lifecycle_closure.py scripts/build_workspace_change_set_lifecycle_closure.py sentientos/workspace_change_set_lifecycle_orchestrator.py scripts/run_workspace_change_set_lifecycle.py
   ```

   The baseline/ratchet contract is documented in [mypy_baseline_ratchet.md](architecture/mypy_baseline_ratchet.md).

7. Bootstrap and build public documentation from the explicit docs dependency
   surface:
   ```bash
   python scripts/build_docs.py --check-deps
   python scripts/build_docs.py --bootstrap-docs
   python scripts/build_docs.py --check-deps
   python scripts/build_docs.py
   ```

   `--bootstrap-docs` installs the same minimal docs requirements declared in
   `pyproject.toml` under the `docs` extra. Reviewers who prefer one install
   command may run `pip install -e .[docs]` instead.

For terminology translation between public engineering language and internal
codenames, see [PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md).

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.
