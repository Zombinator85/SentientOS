# Codex Task Scaffold Path Planner

`sentientos/codex_task_scaffold_path_planner.py` provides a deterministic metadata-only path planner for Codex task scaffolds.

## CLI

`python scripts/plan_codex_task_scaffold_paths.py --task-name ... --preset-id developer_workflow_metadata --summary`

The CLI can emit:
- plan JSON (`--output`)
- scaffold request JSON (`--scaffold-request-output`) compatible with `python -m scripts.build_codex_task_scaffold --input <file>`.

## Safety + boundaries

The planner rejects/warns on:
- absolute paths, traversal, shell metacharacters,
- forbidden authority terms (provider/network/GitHub/action wing/shell/subprocess),
- nonconforming commit titles.

Subsystem remains metadata-only and performs no Codex/provider/network/shell execution.
