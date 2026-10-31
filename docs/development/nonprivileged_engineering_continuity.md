# Nonprivileged engineering continuity

This workflow keeps routine engineering moving when a host lacks dependencies or
has a limited runtime, while preserving the repository's authority, evidence,
and landing controls. It does not grant the agent administrative access.

## Recovery sequence

1. **Classify the observed failure.** A failed assertion, type error, or source
   audit finding is task-caused and must be repaired. Missing packages, an
   unavailable pinned toolchain, package-bootstrap TLS trust, or temporary
   storage limits are environmental. Explicit `Permission denied`, `Operation
   not permitted`, or Administrator-required output is an authority denial.
   Preserve the command, exit code, output, timestamp, workspace SHA, and test
   provenance for each attempt.
2. **Recover once for a routine environmental blocker.** Recover once in a
   bounded attempt. Prefer a disposable
   environment already authorized by the execution platform. Install docs,
   typing, or test dependencies there from the repository's declared groups and
   lockfiles. Use the supported proxy and CA trust supplied for that runtime.
   Keep packages, caches, and generated output in the disposable environment or
   an external evidence directory. Do not modify protected host configuration
   or install system packages to repair a local-only environment.
3. **Keep the boundary narrow.** Do not use privileged containers, mount the
   host Docker socket. Do not forward host credentials, change sandbox/network policy,
   or grant a container broader authority than the operation already has.
   Mount source read-only for read-only checks. If a repository tool requires
   writes, expose only the exact worktree and external evidence directory it
   needs. A container does not make an Administrator-only audit, protected
   memory operation, credential access, publication, or merge nonprivileged.
4. **Record the result, not just the attempt.** Capture the exact command,
   environment/image identity, dependency source, exit status, relevant output,
   workspace revision, and hashes of generated reports. Keep failed and
   successful attempts append-only. Redirect test-run provenance using
   `SENTIENTOS_TEST_RUN_DIR` when generated run files should stay outside the
   source tree. Never claim a check passed because its environment was prepared.
5. **Continue independent authorized work.** If a stage remains blocked after
   the bounded recovery, record its exact blocker and continue work that does
   not depend on it. Do not repeat a known-denied operation, discard its
   evidence, or let the blocked stage imply that unrelated work is complete.
   Return to the blocked stage only when a materially different authorized
   environment or new evidence changes its preconditions.
6. **Keep landing authority intact.** A local environment recovery does not
   count as a passing test, audit, finalizer, or hosted check. Required checks
   must still pass on the exact candidate. The only local privileged deferral
   is the existing `strict_audits` and `audit_immutability` path to the hosted
   `Required / Quality Gate`; its ruleset must require that exact check before
   merge. Keep acceptance manifests, test provenance, evidence custody, PR
   metadata guard, and publication handoff requirements unchanged.

## Finalizer classifications

The landing evaluator distinguishes:

- `repair_required_task_caused`: a required check found a task defect, or an
  environmental blocker coexists with an unclassified task failure.
- `environment_blocked`: required evidence could not be produced because a
  recognized runtime precondition is unavailable. Readiness is denied until
  the check passes.
- `authority_denied`: an explicit permission boundary rejected an operation.
  Do not retry with elevated permissions or relocate the operation to bypass
  that denial.

When independent failures coexist, the finalizer retains the task-repair
decision and all blocker reasons so one category cannot mask another. The
classification changes diagnosis only; it never turns a failed check into a
pass.

See [the landing contract](codex_finalize_landing.md) for canonical finalizer
commands and [the validation contract](codex_validation_and_landing_contract.md)
for acceptance, evidence, and hosted verification requirements.
