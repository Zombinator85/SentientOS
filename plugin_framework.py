"""Plug-in framework for gestures, personas, and actions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from utils import is_headless
import trust_engine as te


class BasePlugin:
    """Base class for gesture/persona/action plug-ins."""

    plugin_type: str = "plugin"
    schema: Dict[str, Any] = {}

    def execute(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Run the plug-in for real hardware."""
        raise NotImplementedError

    def simulate(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate execution in headless mode."""
        return {"simulated": True}

    def run(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Execute or simulate depending on headless mode."""
        if is_headless():
            result = self.simulate(event)
            result.setdefault("simulated", True)
        else:
            result = self.execute(event)
        return result


PLUGINS: dict[str, BasePlugin] = {}
PLUGINS_INFO: dict[str, str] = {}
PLUGIN_STATE: dict[str, bool] = {}
_LOADED_FILES: list[Path] = []


def register_plugin(name: str, plugin: BasePlugin) -> None:
    """Register a plug-in instance."""
    PLUGINS[name] = plugin


def load_plugins() -> None:
    """Load plug-ins from disk."""
    global PLUGINS, PLUGINS_INFO, PLUGIN_STATE, _LOADED_FILES
    PLUGINS = {}
    PLUGINS_INFO = {}
    plugins_dir = Path(os.getenv("GP_PLUGINS_DIR", "gp_plugins"))
    if not plugins_dir.exists():
        return
    _LOADED_FILES = list(plugins_dir.glob("*.py"))
    for fp in _LOADED_FILES:
        spec: dict[str, Any] = {}
        try:
            code = fp.read_text(encoding="utf-8")
            exec(compile(code, str(fp), "exec"), spec)
        except Exception:
            continue
        reg = spec.get("register")
        if callable(reg):
            try:
                reg(register_plugin)
            except Exception:
                pass
        PLUGINS_INFO[fp.stem] = (spec.get("__doc__") or "").strip()
        # Preserve enabled/disabled state across reloads
        PLUGIN_STATE.setdefault(fp.stem, True)

    # Remove state entries for missing plugins
    for name in list(PLUGIN_STATE.keys()):
        if name not in PLUGINS_INFO:
            PLUGIN_STATE.pop(name, None)


def list_plugins() -> dict[str, str]:
    """Return available plug-ins and their descriptions."""
    return dict(PLUGINS_INFO)


def available_plugins(plugin_type: str | None = None) -> list[str]:
    """Return names of enabled plug-ins, optionally filtered by type."""
    names = [n for n, enabled in plugin_status().items() if enabled]
    if plugin_type:
        names = [n for n in names if PLUGINS[n].plugin_type == plugin_type]
    return names


def plugin_status() -> Dict[str, bool]:
    """Return enabled/disabled status for each loaded plugin."""
    return {name: PLUGIN_STATE.get(name, True) for name in PLUGINS_INFO}


def enable_plugin(name: str, *, user: str = "system", reason: str = "enable") -> None:
    if name not in PLUGINS_INFO:
        raise ValueError("Unknown plugin")
    PLUGIN_STATE[name] = True
    te.log_event("plugin_enable", reason, f"Enabled {name}", user)


def disable_plugin(name: str, *, user: str = "system", reason: str = "disable") -> None:
    if name not in PLUGINS_INFO:
        raise ValueError("Unknown plugin")
    PLUGIN_STATE[name] = False
    te.log_event("plugin_disable", reason, f"Disabled {name}", user)


def reload_plugins(*, user: str = "system", reason: str = "reload") -> None:
    load_plugins()
    te.log_event("plugin_reload", reason, "Plugins reloaded", user, {"plugins": list(PLUGINS_INFO)})


def plugin_doc(name: str) -> Dict[str, Any]:
    plug = PLUGINS.get(name)
    if not plug:
        raise ValueError("Unknown plugin")
    return {
        "id": name,
        "type": plug.plugin_type,
        "schema": plug.schema,
        "doc": PLUGINS_INFO.get(name, ""),
    }


def run_plugin(name: str, event: Dict[str, Any] | None = None, *, cause: str = "test", user: str = "plugin") -> Dict[str, Any]:
    """Execute a plug-in and log via the trust engine."""
    plug = PLUGINS.get(name)
    if not plug:
        raise ValueError("Unknown plugin")
    if not PLUGIN_STATE.get(name, True):
        raise ValueError("Plugin disabled")
    evt = event or {}
    result = plug.run(evt)
    explanation = result.get("explanation", f"{name} executed")
    te.log_event(plug.plugin_type, cause, explanation, name, {"event": evt, "result": result, "headless": is_headless()})
    return result


def test_plugin(name: str) -> Dict[str, Any]:
    """Run a plug-in with empty event for testing."""
    return run_plugin(name, {"test": True}, cause="plugin_test")


def model_trigger(name: str, event: Dict[str, Any] | None = None, *, reason: str = "model_request", user: str = "model") -> Dict[str, Any]:
    """Trigger a plug-in from a model with trust logging."""
    return run_plugin(name, event or {}, cause=reason, user=user)


load_plugins()
