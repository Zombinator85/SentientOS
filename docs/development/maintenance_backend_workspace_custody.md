# Backend-independent maintenance workspace custody

Workspace custody is deterministic SentientOS infrastructure. Codex is one
implementation backend, not part of the definition of maintenance custody.

New backend-aware activation profiles and watchdog configurations bind a
`sentientos.maintenance_workspace_custody_config:v1` artifact. It contains the
repository identity and root, external workspace and state roots, exact Git
identity, shared bounds, constraints, and an immutable digest. It contains no
Codex executable, `CODEX_HOME`, model activation, provider credential, or network
configuration.

The supported execution paths are:

```text
maintenance candidate
-> lease
-> implementation request
-> generic workspace custody
-> local Codex backend
-> validation
-> governed landing
```

```text
maintenance candidate
-> lease
-> implementation request
-> generic workspace custody
-> commissioned local-model backend
-> validation
-> governed landing
```

The local-Codex path retains its exact executable, capability probe, sandbox,
profile, session/resume, JSONL, and `CODEX_HOME` requirements. It never silently
falls back to local inference.

The commissioned-local path requires an exact immutable
`sentientos.local_model_activation:v1` in production posture with no fallback.
It requires no Codex executable, invokes no Codex process, and requires no remote
model provider. The model only proposes mediated actions; deterministic
SentientOS code retains workspace, path, lease, budget, validation, landing, and
authority enforcement.

Historical v1 activation-profile, bundle-index, genesis, and watchdog artifacts
remain reconstructable under their original schemas. New backend-polymorphic
profile and genesis renders use their v2 schemas and enumerate only artifacts
for the selected backend; dummy Codex artifacts are forbidden.

The supported claim is narrow: SentientOS supports backend-independent
deterministic maintenance workspace custody, allowing either an explicitly
configured Codex CLI backend or an exact commissioned local-model backend to
perform bounded lease-scoped implementation work, with validation, landing, and
authority remaining outside the model. This does not establish autonomous
recursive self-improvement or grant a model commissioning, validation, commit,
publication, runtime-launch, or generation-zero authority.
