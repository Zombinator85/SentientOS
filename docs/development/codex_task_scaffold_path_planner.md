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
- requests to exercise or expand forbidden authority (provider/network/GitHub/action
  wing/shell/subprocess),
- nonconforming commit titles.

Implementation targets may be existing files despite the historical `new_module` and
`new_cli` field names. Packaged source targets are admitted only beneath the canonical
package roots declared by `pyproject.toml`: `sentientos/`, `api/`, `gui/`, and `apps/`.
The additional workflow/evidence roots are `scripts/`, `tests/`, `docs/`, and
`artifacts/`. A regression check binds the packaged-root constant to both current
packaging declarations so metadata drift fails visibly.

Root matching is path-component aware: admitting `api/` does not admit `apix/` or
`api_evil/`. Absolute paths, traversal, forbidden metacharacters, hidden/sensitive
roots, arbitrary root-level files, and unknown top-level directories remain rejected.
Path validity only classifies a scaffold target; it grants no runtime or effect
authority.

Authority terms are classified occurrence-by-occurrence within their local clause. An
explicit prohibition is permitted. An explicit reduction is permitted only when the
named capability is unambiguously being removed, eliminated, disabled, prohibited,
restricted, or replaced *away from* toward a non-forbidden mechanism. Replacement in
the opposite direction is an authority request. Labels such as “security,” “harden,”
“repair,” and “refactor” do not create exemptions, and a reduction in one clause cannot
mask an exercise request in another. Every occurrence must classify safely; ambiguous
wording remains blocked with `forbidden_authority_surface_requested`.

Subsystem remains metadata-only and performs no Codex/provider/network/shell execution.
