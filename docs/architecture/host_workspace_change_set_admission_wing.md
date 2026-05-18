# Host Workspace Change Set Admission Controller

This wing sits immediately before the existing Host Workspace Change Set Preflight / Planning Wing. It answers one bounded question: is the supplied proposed change-set metadata eligible to be handed to preflight?

Implementation: `sentientos/workspace_change_set_admission.py`.
Optional CLI: `scripts/admit_workspace_change_set.py`.

## Scope

Admission is metadata-only and non-authorizing. It inspects supplied proposal metadata only:

- declared target count;
- proposed target IDs and relative paths;
- declared operation types (`create_file`, `update_file`, `replace_file`);
- declared payload byte counts and declared payload digests when supplied;
- requested authority labels;
- compact contradiction flags.

It emits compact deterministic admission statuses:

- `admission_accepted`
- `admission_accepted_with_warnings`
- `admission_blocked`
- `admission_contradicted`
- `admission_insufficient_metadata`

## Boundary

The admission controller does not read workspace target files, does not check filesystem existence, and does not compute filesystem digests. It does not preflight, build rollback plans, build transaction plans, execute, rollback, verify replay, build lifecycle closure, cleanup, schedule, recurse directories, expand wildcards, or touch unrelated files.

It also does not invoke subprocess, shell, network, provider, prompt assembly/export, service control, power control, fan/PWM control, thermal actuation, package installation, driver installation, plugin execution, generated-code execution, federation import execution, or external tools.

Admission does not prove workspace state and does not authorize execution. A positive decision only means preflight may be attempted next by an explicit caller.

## Blocking and warnings

Admission blocks duplicate target IDs or paths; absolute paths; traversal paths; wildcard-like paths; empty/root paths; directory-like targets; outside-workspace claims; unsupported operations; oversized target counts; oversized declared payload metadata; supplied payload bodies; and forbidden requested authorities such as cleanup/delete, recursive/wildcard/unrelated delete, subprocess, shell, network, provider, prompt, service, power, fan, thermal, hardware, package, driver, plugin, generated-code, or federation execution.

Admission may accept with warnings for conservative non-blocking metadata gaps such as missing declared byte counts or missing declared digests. Missing required structure such as declared target count, proposed targets, target IDs, target paths, or operation metadata yields `admission_insufficient_metadata`.

## CLI

Review a proposal JSON object without invoking preflight:

```bash
python scripts/admit_workspace_change_set.py --proposal <workspace_change_set_proposal_metadata.json> --summary
```

Optionally write exactly one caller-supplied admission artifact:

```bash
python scripts/admit_workspace_change_set.py --proposal <workspace_change_set_proposal_metadata.json> --output <workspace_change_set_admission.json>
```

The artifact contains compact request summaries, findings, blocker and warning codes, declared byte counts/digests, and explicit metadata-only / non-authority boundaries. It does not duplicate target payload bodies, preimage bodies, prompt text, secrets, provider material, runtime handles, or filesystem content.

## Reviewer proof and capability registry

The reviewer proof bundle includes `workspace_change_set_admission_capability.json` and lists the admission CLI command with `proof_command_not_run`; the proof bundle documents but does not run admission by default.

The capability registry marks `workspace_change_set_admission` as implemented with `metadata-admission-only` authority. Preflight, execution, rollback, verification, lifecycle closure, cleanup, scheduling, network, provider, prompt, subprocess, shell, hardware, service, power, fan/PWM, and thermal authority remain separately bounded, deferred, or blocked.

## Tests

Focused tests:

- `tests/test_workspace_change_set_admission.py`
- `tests/test_admit_workspace_change_set_script.py`
- `tests/test_capability_registry.py`
- `tests/test_reviewer_proof_bundle.py`
- `tests/test_build_reviewer_proof_bundle_script.py`
- `tests/test_reviewer_release_readiness_index.py`
