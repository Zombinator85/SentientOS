"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Execute a local Python function via the actuator framework."""
from importlib import import_module
from api.actuator import BaseActuator
import plugin_framework as pf


def register(gui: "CathedralGUI") -> None:
    class PyCallActuator(BaseActuator):
        def execute(self, intent):
            target = intent.get("func")
            if not target or ":" not in target:
                raise ValueError("func must be module:function")
            mod_name, func_name = target.split(":", 1)
            mod = import_module(mod_name)
            func = getattr(mod, func_name)
            args = intent.get("args", [])
            kwargs = intent.get("kwargs", {})
            return {"result": func(*args, **kwargs)}

    pf.register_plugin("pycall", PyCallActuator())
