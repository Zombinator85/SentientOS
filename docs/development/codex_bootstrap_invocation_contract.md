# Codex Bootstrap Invocation Contract

This page seals the supported command-line contract for `scripts/bootstrap_codex_task.py` so repair prompts do not invent bootstrap flags and do not continue after invocation failures.

## Supported CLI flags

The bootstrap CLI currently supports exactly these flags:

- `--task-name` (required)
- `--task-goal` (required)
- `--preset-id`
- `--subsystem-kind`
- `--commit-scope`
- `--output-dir`
- `--summary-output`
- `--plan-output`
- `--scaffold-output`
- `--prompt-output`
- `--verifier-output`
- `--summary`
- `--emit-prompt`
- `--new-module`
- `--new-cli`
- `--test-path`
- `--doc-path`
- `--existing-target` (repeatable; tracked-file maintenance only)
- `--capability-id`
- `--proof-bundle-artifact-kind`
- `--commit-title`

Do not use undocumented aliases or inferred flags. In particular, `--existing-module` and `--existing-cli` remain unsupported. `--existing-target` is a separate, bounded interface: it accepts only an already tracked, regular, non-symlink file within the root authorized by the selected maintenance subsystem. It does not admit a new scaffold path or grant execution authority.

## Invocation errors are not bootstrap decisions

Unsupported bootstrap flags are command invocation errors raised by argument parsing. They are not `ready`, `ready_with_warnings`, `blocked`, `insufficient`, or `failed` bootstrap decisions, and they do not produce an implementation contract.

If bootstrap exits nonzero because of unsupported arguments, stop immediately, fix the command line, and rerun bootstrap before implementation. Do not reinterpret an argument-parser failure as a blocked bootstrap artifact, and do not proceed from any prompt, scaffold, or summary that was not produced by a successful invocation.

## Repair-task path pattern

For repair tasks, use `--new-module` and `--new-cli` only when intentionally naming the module or CLI path that the scaffold should reason about, even if that path already exists. These flags identify the path surface for planner/scaffold metadata; they are not promises that the filesystem path is absent.

If no module or CLI path needs scaffold reasoning, omit `--new-module` and `--new-cli` and list the explicit delta-specific files elsewhere in the task prompt. Do not invent `--existing-module`, `--existing-cli`, or similar unsupported bootstrap flags.

Existing-file maintenance uses one of three explicit subsystem classifications:

- `ci_workflow_maintenance`: existing files under `.github/workflows/` only.
- `construction_custody_reconciliation`: existing files under `work/construction/` only.
- `bootstrap_reliability_repair`: the bootstrapper, path planner, scaffold, CLI, their named tests, and their two development guides only.
- `causal_introspection_observation_maintenance`: `sentientos/causal_introspection.py`, its focused test, and `docs/architecture/causal_introspection_topology.md` only.

Pass each target with `--existing-target`. The planner checks the literal relative path, regular-file type, symlink-free path, tracked status, and subsystem-specific allowlist. It rejects missing, untracked, traversal, and out-of-scope targets. These maintenance classifications cannot declare new module or CLI scaffold paths. Existing-target admission is planning metadata, not a permission to mutate the file or perform an effect.

`subsystem_kind` is required by the scaffold even though the planner can independently produce default path metadata. Omitting it causes `insufficient_required_metadata`; current output also names `missing_subsystem_kind`. The planner/scaffold/verifier summaries identify which layer blocked. This is an invocation classification error, not an authority denial.

## Construction-mode exception

The Codex task scaffold is for producing a task prompt and its proposed metadata. It is not a universal authorization gate for every repository change. For a bounded `[untested]` construction increment that is explicitly authorized under the construction exception in `AGENTS.md`, do not run this scaffold or the full landing lifecycle merely as a ritual. Preserve that explicit task authorization and mark the result unverified. If a task or applicable workflow actually requires this bootstrap, use supported arguments including `--subsystem-kind`; a `blocked` result remains diagnostic and must not be treated as an implementation contract. Independent task authorization, when present, does not come from the blocked artifact.

## Existing-file maintenance example

```bash
PYTHONPATH=. python scripts/bootstrap_codex_task.py \
  --task-name "CI workflow maintenance" \
  --task-goal "Update the existing .github/workflows/ci.yml source-validation job" \
  --subsystem-kind ci_workflow_maintenance \
  --existing-target .github/workflows/ci.yml \
  --summary-output /tmp/ci-maintenance-bootstrap.json \
  --summary
```

Use `construction_custody_reconciliation` with tracked `work/construction/...` targets, or `bootstrap_reliability_repair` with only the bootstrap-owned files and tests listed above. For a narrow bootstrap self-repair, the canonical scaffold classification is `bootstrap_reliability_repair`; it does not add a capability, principal, or requested effect.

## Minimal supported example

```bash
PYTHONPATH=. python scripts/bootstrap_codex_task.py \
  --task-name "Example narrow repair" \
  --task-goal "Document the repair goal." \
  --subsystem-kind developer_workflow_metadata \
  --commit-scope developer \
  --commit-title "[codex:developer] document repair goal" \
  --test-path tests/test_bootstrap_codex_task_script.py \
  --doc-path docs/development/codex_bootstrap_invocation_contract.md \
  --summary-output /tmp/codex_bootstrap.summary.json \
  --summary
```

## Supported path-surface example

```bash
PYTHONPATH=. python scripts/bootstrap_codex_task.py \
  --task-name "Example path repair" \
  --task-goal "Repair bootstrap path metadata." \
  --subsystem-kind developer_workflow_metadata \
  --commit-scope developer \
  --new-module sentientos/codex_task_bootstrapper.py \
  --new-cli scripts/bootstrap_codex_task.py \
  --test-path tests/test_bootstrap_codex_task_script.py \
  --doc-path docs/development/codex_bootstrap_invocation_contract.md \
  --commit-title "[codex:developer] repair bootstrap path metadata" \
  --summary
```

## Preset selection versus subsystem classification

`preset_id` explicitly selects a registered scaffold preset, while `subsystem_kind`
classifies the task surface. When `preset_id` is omitted, a subsystem that is itself a
registered preset ID retains compatibility verification. A specialized subsystem that
is not in the preset catalog does not implicitly select a preset and is not reported as
an unknown preset. An explicitly supplied unknown `preset_id` is still reported.
