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
- `--capability-id`
- `--proof-bundle-artifact-kind`
- `--commit-title`

Do not use undocumented aliases or inferred flags. In particular, repair prompts must not use `--existing-module` or `--existing-cli`; those names are unsupported.

## Invocation errors are not bootstrap decisions

Unsupported bootstrap flags are command invocation errors raised by argument parsing. They are not `ready`, `ready_with_warnings`, `blocked`, `insufficient`, or `failed` bootstrap decisions, and they do not produce an implementation contract.

If bootstrap exits nonzero because of unsupported arguments, stop immediately, fix the command line, and rerun bootstrap before implementation. Do not reinterpret an argument-parser failure as a blocked bootstrap artifact, and do not proceed from any prompt, scaffold, or summary that was not produced by a successful invocation.

## Repair-task path pattern

For repair tasks, use `--new-module` and `--new-cli` only when intentionally naming the module or CLI path that the scaffold should reason about, even if that path already exists. These flags identify the path surface for planner/scaffold metadata; they are not promises that the filesystem path is absent.

If no module or CLI path needs scaffold reasoning, omit `--new-module` and `--new-cli` and list the explicit delta-specific files elsewhere in the task prompt. Do not invent `--existing-module`, `--existing-cli`, or similar unsupported bootstrap flags.

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
