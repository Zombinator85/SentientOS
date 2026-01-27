"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Demo plugin that exposes a simple ``hello`` actuator.

The actuator just returns a greeting with the provided name.  This file is
used in the test-suite to demonstrate plugin discovery.
"""

import plugin_framework as pf


def register(gui: "CathedralGUI") -> None:
    class HelloPlugin(pf.BasePlugin):
        plugin_type = "greeting"
        allowed_postures = ["normal"]
        requires_epoch = True
        capabilities = []

        def execute(self, intent, context=None):
            name = intent.get("name", "world")
            return {"hello": name}

    pf.register_plugin("hello", HelloPlugin())
