# Codex task bootstrapper

`sentientos/codex_task_bootstrapper.py` composes planner + scaffold generator + scaffold verifier (+ optional preset verifier) into one deterministic metadata-only bootstrap flow.

## API

- `bootstrap_codex_task(request, include_preset_verifier=True)`
- `write_bootstrap_artifacts(...)`

## CLI

`python scripts/bootstrap_codex_task.py --task-name ... --task-goal ... --subsystem-kind developer_workflow_metadata --output-dir artifacts/codex --summary`

## Authority-definition registration

`authority_definition_registration` is the dedicated governance-only task
classification for extending the canonical `AUTHORITY_DEFINITIONS` vocabulary.
Its artifact contains exactly one complete definition, the introducing task,
and explicit operator-approval evidence bound by digest to both. The approval
must use schema `sentientos.authority_definition_operator_approval:v1`, status
`approved`, a non-empty evidence and operator identity label, and exact
capability, definition-digest, and task-name bindings. Ordinary coding prose is
not approval evidence.

Registration may change only the canonical definition metadata and directly
associated schema/validation, bootstrap, tests, documentation, acceptance, and
artifact surfaces. It rejects runtime mutations and any simultaneous capability
ID, principal, or effect request. It creates no lease or grant, performs no
effect, and does not mutate ControlPlaneKernel, RuntimeGovernor, actuator,
transport, provider, model-execution, or capability-runtime state. The
registration implementation returns a new immutable catalog view rather than
mutating the process-global catalog; repository review remains the durable
catalog-change boundary.

The lifecycle is deliberately two-stage:

1. The operator decides that SentientOS should gain a new class of ability.
2. One bounded authority definition is registered with exact subsystem kinds,
   principal kinds, effects, affirmative preconditions, forbidden phrases,
   approval requirements, and rationale.
3. The definition grants nothing.
4. A later implementation task requests the exact capability ID, subsystem,
   principal, effects, and affirmative preconditions through the existing
   authority-admission mechanism.
5. Implementation and validation occur, while any runtime authority remains
   separately governed.

Duplicate or malformed IDs, empty or wildcard surfaces, duplicate effects,
contradictory goal semantics, incomplete metadata, absent or mismatched
approval, multiple definitions, effect requests, and runtime mutations fail
closed. The proposed definition is never consulted to authorize its own
registration and is unavailable for effects in that task. **Capability growth
must be possible without capability self-authorization. Defining authority is
not exercising authority.**

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
