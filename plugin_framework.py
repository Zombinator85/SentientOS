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
_LOADED_FILES: list[Path] = []


def register_plugin(name: str, plugin: BasePlugin) -> None:
    """Register a plug-in instance."""
    PLUGINS[name] = plugin


def load_plugins() -> None:
    """Load plug-ins from disk."""
    global PLUGINS, PLUGINS_INFO, _LOADED_FILES
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


def list_plugins() -> dict[str, str]:
    """Return available plug-ins and their descriptions."""
    return dict(PLUGINS_INFO)


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
    evt = event or {}
    result = plug.run(evt)
    explanation = result.get("explanation", f"{name} executed")
    te.log_event(plug.plugin_type, cause, explanation, name, {"event": evt, "result": result, "headless": is_headless()})
    return result


def test_plugin(name: str) -> Dict[str, Any]:
    """Run a plug-in with empty event for testing."""
    return run_plugin(name, {"test": True}, cause="plugin_test")


load_plugins()
