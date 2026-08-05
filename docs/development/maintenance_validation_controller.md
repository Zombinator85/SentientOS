# Maintenance validation controller

The maintenance validation controller consumes a local-Codex foreman result that is exactly `implementation_ready_for_validation` and turns it into bounded evidence. It is validation authority, not implementation authority and not commit or publication authority.

## Authority and grammar

Validation execution requires `validation_execute` plus `repository_state_read`. Corrective continuation additionally requires the foreman's explicit implementation authorities: `implementation_agent_session`, `implementation_process_execute`, `implementation_instruction_disclosure`, `remote_model_invocation`, `repository_workspace_provision`, and `repository_workspace_modify`. None are implicit.

The closed lease-bound expectation grammar is: `pytest_node:<exact pytest node ID>`, `mypy_path:<repository-relative Python path>`, `mypy_baseline`, `git_diff_check`, `docs_check_deps`, `docs_build`, `prompt_boundaries`, `strict_audits`, and `audit_immutability`. Arbitrary commands, shell fragments, redirects, interpolation, absolute paths, traversal, unknown kinds, empty pytest nodes, and out-of-scope mypy paths fail closed.

## Planning and matrix exclusion

Planning binds the policy digest, lease, attempt, implementation session, Codex thread, foreman result, worktree descriptor, invocation, change manifest, patch, changed paths, stage IDs, argv arrays, budgets, environment-name-set digest, and plan digest. The same inputs produce byte-identical plan bytes.

Every plan includes worktree/result/source baseline verification and `git diff --check`. Python source changes trigger targeted mypy and the baseline checker. Documentation changes trigger docs dependency checking and docs build. Governance, authority, prompt-boundary, audit, capability, lifecycle, foreman, journal, lease, validation, or security-control surfaces trigger prompt-boundary verification, strict audits, and audit immutability.

Ordinary validation never starts `scripts/run_work_item_review_packet_matrix.py`, does not wait for hosted checks, does not poll remote statuses, and records `exhaustive_matrix_status = not_requested_for_proportionate_validation` with matrix invocation count zero.

## Execution, custody, and drift proof

Commands are constructed only as argv arrays and launched with `shell=False` in the exact detached worktree. The sanitized environment records names only and sets external scratch/cache roots such as `PYTHONDONTWRITEBYTECODE`, `PYTHONPYCACHEPREFIX`, `MYPY_CACHE_DIR`, and `TMPDIR` without persisting secret values.

Each stage writes an immutable `sentientos.maintenance_validation_command_result:v1` under the external state root with argv digest, cwd/worktree digest, environment-name-set digest, timings, PID/process-group evidence, bounded stdout/stderr tails, output digests, failure class, and result digest. The aggregate `sentientos.maintenance_validation_result:v1` binds command result digests, outcomes, skipped stages, total and cumulative validation budget, source-drift proof, matrix-not-requested status, terminal status, correctability, result digest, and journal terminal event.

After each stage and at terminal proof the controller rereads HEAD, branch state, and the complete source change manifest. Any commit, branch, source drift, or out-of-scope proof change returns `validation_workspace_changed_during_proof` and is not reverted automatically.

## Journal, correction, and recovery

Validation events are cycle-bound and historical: `validation_started` requires the latest successful implementation attempt, terminal validation events must match the active validation reference, and snapshots retain all cycles while exposing the latest result. `ready_to_commit_recorded` must bind the latest passing cycle and implementation attempt. A later corrective attempt invalidates commit readiness.

Correctable implementation failures can create a sealed `sentientos.maintenance_corrective_continuation:v1` envelope. The controller can repair a failed implementation without the operator relaying test output, but correction remains inside the original immutable lease. Infrastructure and integrity failures are not sent to Codex as code-repair instructions. Same-thread continuation is a new maintenance attempt and session, with a new retry ordinal, in the same detached worktree and same Codex thread.

Recovery reuses exact identities, does not rerun completed command results, appends only missing events, does not consume another retry, and does not create another attempt or session. One deterministic per-task lock controls concurrency.

Terminal statuses include `validation_ready_for_commit`, `validation_failed_correctable`, `validation_failed_terminal`, `validation_blocked`, `validation_budget_exhausted`, `validation_timed_out`, `validation_interrupted`, `validation_workspace_changed_during_proof`, `corrective_continuation_started`, `corrective_continuation_completed`, `corrective_continuation_blocked`, `corrective_retry_limit_reached`, `corrective_attempt_limit_reached`, `corrective_lease_expired`, `controller_recovery_required`, and `controller_integrity_failed`.

Passing validation does not commit. The next remaining stage is exact commit and asynchronous publication custody.
