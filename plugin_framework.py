"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Plug-in framework for gestures, personas, and actions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from utils import is_headless
import trust_engine as te
import reflection_stream as rs
import importlib.util


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
PLUGIN_HEALTH: dict[str, Dict[str, Any]] = {}
PROPOSALS: dict[str, Dict[str, Any]] = {}
_LOADED_FILES: list[Path] = []


def register_plugin(name: str, plugin: BasePlugin) -> None:
    """Register a plug-in instance."""
    PLUGINS[name] = plugin


def load_plugins() -> None:
    """Load plug-ins from disk using importlib."""
    global PLUGINS, PLUGINS_INFO, PLUGIN_STATE, _LOADED_FILES
    PLUGINS = {}
    PLUGINS_INFO = {}
    plugins_dir = Path(os.getenv("GP_PLUGINS_DIR", "gp_plugins"))
    if not plugins_dir.exists():
        return
    _LOADED_FILES = list(plugins_dir.glob("*.py"))
    for fp in _LOADED_FILES:
        try:
            spec = importlib.util.spec_from_file_location(fp.stem, fp)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:  # pragma: no cover - load errors
            te.log_event("plugin_load_error", "load", str(e), fp.stem)
            continue
        reg = getattr(module, "register", None)
        if callable(reg):
            try:
                reg(register_plugin)
            except Exception as e:  # pragma: no cover - plugin init issues
                te.log_event("plugin_register_error", "load", str(e), fp.stem)
                continue
        else:
            te.log_event("plugin_invalid", "load", "missing register", fp.stem)
            continue
        PLUGINS_INFO[fp.stem] = (getattr(module, "__doc__", "") or "").strip()
        PLUGIN_STATE.setdefault(fp.stem, True)
        PLUGIN_HEALTH.setdefault(fp.stem, {"status": "ok"})

    # Remove state entries for missing plugins
    for name in list(PLUGIN_STATE.keys()):
        if name not in PLUGINS_INFO:
            PLUGIN_STATE.pop(name, None)
            PLUGIN_HEALTH.pop(name, None)


def list_plugins() -> dict[str, str]:
    """Return available plug-ins and their descriptions."""
    return dict(PLUGINS_INFO)


def list_health() -> Dict[str, Dict[str, Any]]:
    """Return current health state for plugins."""
    return {n: dict(v) for n, v in PLUGIN_HEALTH.items()}


def list_proposals() -> Dict[str, Dict[str, Any]]:
    """Return current plugin proposals."""
    return {n: dict(v) for n, v in PROPOSALS.items()}


def propose_plugin(name: str, url: str, *, user: str = "model") -> None:
    """Record a model suggestion for a new or updated plugin."""
    PROPOSALS[name] = {"url": url, "status": "pending"}
    te.log_event("plugin_proposal", "proposed", f"{name} -> {url}", user)


def approve_proposal(name: str, *, user: str = "user") -> bool:
    prop = PROPOSALS.get(name)
    if not prop or prop.get("status") != "pending":
        return False
    dest = None
    temp_path = None
    try:
        src = Path(prop["url"])
        dest_dir = Path(os.getenv("GP_PLUGINS_DIR", "gp_plugins"))
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / f"{name}.py"
        temp_path = dest_dir / f".{name}.installing"
        temp_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        temp_path.replace(dest)
        load_plugins()
        if name not in PLUGINS_INFO:
            raise RuntimeError(f"plugin '{name}' did not register after install")
        prop["status"] = "installed"
        PLUGIN_STATE[name] = True
        PLUGIN_HEALTH[name] = {"status": "ok"}
        te.log_event("plugin_installed", "approval", f"Installed {name}", user)
        return True
    except Exception as e:  # pragma: no cover - install failures
        prop["status"] = "failed"
        for path in (temp_path, dest):
            if path is None:
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            load_plugins()
        except Exception:
            pass
        te.log_event("plugin_install_failed", "approval", str(e), user)
        return False


def deny_proposal(name: str, *, user: str = "user") -> bool:
    prop = PROPOSALS.get(name)
    if not prop:
        return False
    prop["status"] = "denied"
    te.log_event("plugin_denied", "user", f"Denied {name}", user)
    return True


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
    PLUGIN_HEALTH[name] = {"status": "ok"}
    te.log_event("plugin_enable", reason, f"Enabled {name}", user)


def disable_plugin(name: str, *, user: str = "system", reason: str = "disable") -> None:
    if name not in PLUGINS_INFO:
        raise ValueError("Unknown plugin")
    PLUGIN_STATE[name] = False
    PLUGIN_HEALTH[name] = {"status": "disabled"}
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
    try:
        result = plug.run(evt)
        PLUGIN_HEALTH[name] = {"status": "ok"}
        explanation = result.get("explanation", f"{name} executed")
        te.log_event(plug.plugin_type, cause, explanation, name, {"event": evt, "result": result, "headless": is_headless()})
        rs.log_event(name, "action", cause, "executed", explanation)
        return result
    except Exception as e:  # pragma: no cover - rare
        err = str(e)
        PLUGIN_HEALTH[name] = {"status": "error", "error": err}
        te.log_event("plugin_error", "run_exception", err, name)
        rs.log_event(name, "failure", "run_exception", "error", err)
        try:
            load_plugins()
            PLUGIN_HEALTH[name] = {"status": "reloaded"}
            te.log_event("plugin_auto_reload", "auto", f"Reloaded {name}", name)
            rs.log_event(name, "recovery", "auto_reload", "reloaded", "auto reload")
        except Exception as e2:  # pragma: no cover - reload issues
            PLUGIN_HEALTH[name] = {"status": "failed_reload", "error": str(e2)}
            te.log_event("plugin_reload_failed", "auto", str(e2), name)
            rs.log_event(name, "failure", "reload_failed", "disable", str(e2))
        PLUGIN_STATE[name] = False
        te.log_event("plugin_auto_disable", "auto", f"Disabled {name}", name)
        rs.log_event(name, "escalation", "auto_disable", "disabled", err)
        return {"error": err}


def test_plugin(name: str) -> Dict[str, Any]:
    """Run a plug-in with empty event for testing."""
    return run_plugin(name, {"test": True}, cause="plugin_test")


def model_trigger(name: str, event: Dict[str, Any] | None = None, *, reason: str = "model_request", user: str = "model") -> Dict[str, Any]:
    """Trigger a plug-in from a model with trust logging."""
    return run_plugin(name, event or {}, cause=reason, user=user)


load_plugins()
