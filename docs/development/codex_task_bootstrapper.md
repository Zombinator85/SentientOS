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

## Authority-intent boundary

Bootstrap distinguishes explicit prohibition, explicit authority reduction, and
authority exercise or expansion. Reduction maintenance can proceed only when each named
forbidden capability is locally and directionally described as being removed or
narrowed. Replacing a forbidden capability with a non-forbidden mechanism may qualify;
introducing the forbidden capability as a replacement does not. Mixed clauses are
checked independently, generic hardening labels grant no exception, and ambiguous
requests fail closed with `forbidden_authority_surface_requested`.

No Codex invocation, provider calls, GitHub, shell/subprocess delegation, or runtime authority expansion is performed.
