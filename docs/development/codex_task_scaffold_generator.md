# Codex Whole-System Task Scaffold Generator

`sentientos/codex_task_scaffold.py` and `scripts/build_codex_task_scaffold.py` provide deterministic developer-workflow scaffolding.

## Purpose

Generate a complete Codex task prompt scaffold from compact metadata so operators do not rewrite doctrine, validation, and boundary clauses for every subsystem task.

## Non-authority boundary

- Developer workflow scaffolding only.
- No Codex invocation.
- No provider/network/GitHub calls.
- No branch/PR/issue mutation.
- No shell/subprocess execution from library code.

## Inputs

Required: `task_name`, `task_goal`, `subsystem_kind`.

Optional: mode, deliverables, expected module/CLI/test/doc paths, capability/proof references, validation commands, commit title, and explicit artifact output paths.

## Outputs

- Deterministic JSON scaffold payload.
- Optional deterministic prompt text artifact.
- Compact statuses (`codex_task_scaffold_*`).

## CLI

```bash
python scripts/build_codex_task_scaffold.py --task-name ... --task-goal ... --subsystem-kind ... --summary
```

Use `--output` and `--prompt-output` for explicit artifact writes.
