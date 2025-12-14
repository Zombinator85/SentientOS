# Plugin & Extension Developer Guide

External contributors can extend SentientOS by adding plug-ins or service extensions. Follow these procedures to keep the audit clean:

1. Define a `register(register_plugin)` entrypoint that registers a `BasePlugin` instance.
2. Include a short module docstring explaining the purpose and required privileges.
3. Log all actions via the trust engine (`plugin_framework`); never write to log files directly.
4. Keep dependencies minimal and mention them in your PR description.

Use `python plugins_cli.py status` to verify your plugin loads correctly.

GUI panels can be dropped in the `plugins/` directory. `plugin_bus.watch_plugins()`
automatically imports any `.py` file and calls its `register(gui)` function.
Hot edits are detected via the `watchdog` observer so panels reload live without
restarting the GUI.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
