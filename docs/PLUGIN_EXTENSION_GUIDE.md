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

GUI panels can be dropped in the `plugins/` directory. `plugin_bus.watch_plugins()`
automatically imports any `.py` file and calls its `register(gui)` function.
Hot edits are detected via the `watchdog` observer so panels reload live without
restarting the GUI.

That older mixed `plugins/` architecture is separate and is not migrated or
repaired by the `plugin_framework` boundary. In particular,
`plugins/pycall.py` retains its historical module/function mechanism as a
separate follow-up surface.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
