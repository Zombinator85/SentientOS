# Codex task bootstrapper

`sentientos/codex_task_bootstrapper.py` composes planner + scaffold generator + scaffold verifier (+ optional preset verifier) into one deterministic metadata-only bootstrap flow.

## API

- `bootstrap_codex_task(request, include_preset_verifier=True)`
- `write_bootstrap_artifacts(...)`

## CLI

`python scripts/bootstrap_codex_task.py --task-name ... --task-goal ... --subsystem-kind developer_workflow_metadata --output-dir artifacts/codex --summary`

Outputs optional artifacts:
- summary JSON
- plan JSON
- scaffold JSON
- prompt text
- verifier report JSON

No Codex invocation, provider calls, GitHub, shell/subprocess delegation, or runtime authority expansion is performed.
