# Canonical installation-state initialization

The operator-facing initializer creates only the canonical machine-scoped state
directory by delegating to `InstallationStateRegistry.system().open(...,
create=True)`, then independently reopens the same identity:

```console
PYTHONPATH=. python scripts/initialize_installation_state.py \
  --installation-identity primary
```

On Linux the registry fixes custody beneath
`/var/lib/sentientos/durable-state/installations/<identity>/state`. The command
does not accept an alternate root. An installation identity is a stable local
identifier only: initialization grants no catalog, model, network, execution,
commissioning, activation, serving, inference, or transition authority.

The command is idempotent for an existing safe directory chain. Invalid
identities, unsupported platforms, symlinks, unsafe ownership or modes, and
reopen mismatches fail closed.
