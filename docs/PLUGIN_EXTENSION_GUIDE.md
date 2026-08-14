# Plugin & Extension Developer Guide

The `plugin_framework` admits **repository-owned, source-explicit built-ins
only**. Its complete current built-in set is declared in
`sentientos/plugin_builtin_registry.py`; currently that set is `wave_hand`.
`initialize_plugins()` idempotently adds missing built-ins without replacing
valid instances or deleting deliberate internal registrations. `load_plugins()`
is a compatibility name for that same built-in-only operation. Reload reasserts
missing built-ins, preserves enable/disable state and internal registrations,
and never scans a directory.

`GP_PLUGINS_DIR` is retired. Directory placement, a `.py` suffix, a
`register()` callback, or a proposal does not grant executable authority.
Proposals remain review metadata: approval returns
`external_activation_unsupported` without reading, copying, importing, or
registering proposed source.

Built-ins still declare posture, epoch, and runtime capabilities. The current
in-process API monkeypatching is runtime defense in depth for already admitted
repository code; it is not import isolation or a process security boundary.
Externally supplied executable extensions require a future, separately designed
identity, packaging, custody, and isolation contract.

Use `python plugins_cli.py status` to inspect admitted built-ins.

The older mixed-directory executable loader is retired. `plugin_bus.PluginBus`
retains only deliberate registration of already-admitted in-memory objects;
its `load`, `load_all`, and `watch_plugins` compatibility methods do not inspect
or execute files. The packaged `sentientos.plugin_loader.PluginLoader` is also
inert: it does not create or scan a plugin directory and does not start a
watcher. Live `.py` hot reload is retired.

The legacy `TRUSTED` marker was checked only after Python had executed, so it
was never an execution-security boundary and is retired. The installed
distribution `sentientos.plugins` entry-point group and its automatic loading
are retired too. Directory placement and package metadata confer no executable
extension authority.

Historical files under the root `plugins/` directory, including
`plugins/pycall.py`, remain inert archaeology and separate cleanup candidates;
the retired loaders no longer provide an execution path from their presence to
their source. This does not claim those files themselves were made safe or that
all dynamic imports in the repository were removed. The independently used
telegram, webhook-status-monitor, and bridge-watchdog modules remain ordinary
modules, not implicit plugins.

Externally supplied executable extensions remain a future, separately designed
identity, package, custody, and isolation problem. They are not absorbed into
the repository-built-in-only `plugin_framework` registry established by PR
#2026.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
