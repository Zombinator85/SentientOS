"""Execute a local Python function via the actuator framework."""
from importlib import import_module
from api.actuator import BaseActuator


def register(reg):
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

    reg("pycall", PyCallActuator())
