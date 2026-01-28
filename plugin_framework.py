"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Plug-in framework for gestures, personas, and actions."""

import builtins
import contextlib
import importlib.util
import inspect
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, Iterator, Sequence

import reflection_stream as rs
import trust_engine as te
from resident_kernel import ResidentKernel
from sentientos.embodiment import embodiment_digest
from utils import is_headless


class PluginDeclarationError(ValueError):
    """Raised when plugin capability declarations are missing or invalid."""


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Read-only execution context for plugins."""

    plugin_name: str
    allowed_postures: tuple[str, ...]
    requires_epoch: bool
    capabilities: tuple[str, ...]
    posture: str
    epoch_id: int | None
    epoch_active: bool
    caller_module: str | None
    headless: bool
    dry_run: bool
    governance: MappingProxyType
    embodiment: MappingProxyType

    def _require_capability(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise PermissionError(f"Capability '{capability}' is required")

    def emit_voice(self, text: str) -> Dict[str, Any]:
        """Emit speech if the plugin is authorized for TTS."""
        self._require_capability("tts")
        te.log_event(
            "plugin_voice",
            "emit",
            text,
            self.plugin_name,
            {"caller": self.caller_module, "posture": self.posture, "epoch_id": self.epoch_id},
        )
        return {"ok": True, "text": text}

    def record_memory(self, text: str, *, tags: Sequence[str] | None = None, source: str = "plugin") -> str:
        """Append to memory ledger if authorized."""
        self._require_capability("memory")
        import memory_manager as mm

        return mm.append_memory(text, tags=list(tags or []), source=source)

    def log_presence(self, category: str, action: str, description: str) -> None:
        """Write a presence ledger entry if authorized."""
        self._require_capability("presence")
        import presence_ledger as pl

        pl.log(category, action, description)


class BasePlugin:
    """Base class for gesture/persona/action plug-ins."""

    plugin_type: str = "plugin"
    schema: Dict[str, Any] = {}
    allowed_postures: Sequence[str] | None = None
    requires_epoch: bool | None = None
    capabilities: Sequence[str] | None = None

    def execute(self, event: Dict[str, Any], context: PluginContext | None = None) -> Dict[str, Any]:
        """Run the plug-in for real hardware."""
        raise NotImplementedError

    def simulate(self, event: Dict[str, Any], context: PluginContext | None = None) -> Dict[str, Any]:
        """Simulate execution in headless mode."""
        return {"simulated": True}

    def run(
        self,
        event: Dict[str, Any],
        *,
        context: PluginContext | None = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute or simulate depending on headless mode."""
        if is_headless() or dry_run:
            result = _invoke_plugin_method(self.simulate, event, context)
            result.setdefault("simulated", True)
        else:
            result = _invoke_plugin_method(self.execute, event, context)
        return result


PLUGINS: dict[str, BasePlugin] = {}
PLUGINS_INFO: dict[str, str] = {}
PLUGIN_STATE: dict[str, bool] = {}
PLUGIN_HEALTH: dict[str, Dict[str, Any]] = {}
PLUGIN_DECLARATIONS: dict[str, Dict[str, Any]] = {}
PROPOSALS: dict[str, Dict[str, Any]] = {}
_LOADED_FILES: list[Path] = []
_KERNEL: ResidentKernel | None = ResidentKernel()


def set_kernel(kernel: ResidentKernel | None) -> None:
    """Set the kernel used for plugin posture/epoch checks."""
    global _KERNEL
    _KERNEL = kernel


def get_kernel() -> ResidentKernel | None:
    """Return the configured kernel (if any)."""
    return _KERNEL


def _invoke_plugin_method(
    method: Callable[..., Dict[str, Any]],
    event: Dict[str, Any],
    context: PluginContext | None,
) -> Dict[str, Any]:
    try:
        sig = inspect.signature(method)
    except (TypeError, ValueError):
        return method(event)
    params = list(sig.parameters.values())
    if len(params) >= 2:
        return method(event, context)
    return method(event)


def _normalize_declaration(name: str, plugin: BasePlugin) -> Dict[str, Any]:
    allowed_postures = getattr(plugin, "allowed_postures", None)
    requires_epoch = getattr(plugin, "requires_epoch", None)
    capabilities = getattr(plugin, "capabilities", None)

    if (
        allowed_postures is None
        or not isinstance(allowed_postures, Sequence)
        or isinstance(allowed_postures, (str, bytes))
        or not allowed_postures
    ):
        raise PluginDeclarationError(f"{name} missing allowed_postures declaration")
    if not all(isinstance(p, str) and p.strip() for p in allowed_postures):
        raise PluginDeclarationError(f"{name} allowed_postures must be non-empty strings")
    if requires_epoch is None or not isinstance(requires_epoch, bool):
        raise PluginDeclarationError(f"{name} missing requires_epoch declaration")
    if (
        capabilities is None
        or not isinstance(capabilities, Sequence)
        or isinstance(capabilities, (str, bytes))
    ):
        raise PluginDeclarationError(f"{name} missing capabilities declaration")
    if not all(isinstance(c, str) and c.strip() for c in capabilities):
        raise PluginDeclarationError(f"{name} capabilities must be strings")

    return {
        "allowed_postures": tuple(p.strip() for p in allowed_postures),
        "requires_epoch": requires_epoch,
        "capabilities": tuple(c.strip() for c in capabilities),
    }


@contextlib.contextmanager
def _sandbox_capabilities(capabilities: Sequence[str]) -> Iterator[None]:
    caps = set(capabilities)
    restores: list[Callable[[], None]] = []

    def _restore(attr_owner: object, attr_name: str, original: object) -> None:
        restores.append(lambda: setattr(attr_owner, attr_name, original))

    if "filesystem" not in caps:
        original_open = builtins.open

        def blocked_open(*_args, **_kwargs):
            raise PermissionError("filesystem capability required")

        builtins.open = blocked_open  # type: ignore[assignment]
        _restore(builtins, "open", original_open)

        original_os_open = os.open

        def blocked_os_open(*_args, **_kwargs):
            raise PermissionError("filesystem capability required")

        os.open = blocked_os_open  # type: ignore[assignment]
        _restore(os, "open", original_os_open)

    if "subprocess" not in caps:
        import subprocess

        original_popen = subprocess.Popen
        original_run = subprocess.run
        original_call = subprocess.call
        original_check_call = subprocess.check_call
        original_check_output = subprocess.check_output

        def blocked_subprocess(*_args, **_kwargs):
            raise PermissionError("subprocess capability required")

        subprocess.Popen = blocked_subprocess  # type: ignore[assignment]
        subprocess.run = blocked_subprocess  # type: ignore[assignment]
        subprocess.call = blocked_subprocess  # type: ignore[assignment]
        subprocess.check_call = blocked_subprocess  # type: ignore[assignment]
        subprocess.check_output = blocked_subprocess  # type: ignore[assignment]
        _restore(subprocess, "Popen", original_popen)
        _restore(subprocess, "run", original_run)
        _restore(subprocess, "call", original_call)
        _restore(subprocess, "check_call", original_check_call)
        _restore(subprocess, "check_output", original_check_output)

        original_os_system = os.system
        original_os_popen = os.popen

        def blocked_os_system(*_args, **_kwargs):
            raise PermissionError("subprocess capability required")

        os.system = blocked_os_system  # type: ignore[assignment]
        os.popen = blocked_os_system  # type: ignore[assignment]
        _restore(os, "system", original_os_system)
        _restore(os, "popen", original_os_popen)

    if "network" not in caps:
        original_socket = socket.socket
        original_create_connection = socket.create_connection

        def blocked_socket(*_args, **_kwargs):
            raise PermissionError("network capability required")

        socket.socket = blocked_socket  # type: ignore[assignment]
        socket.create_connection = blocked_socket  # type: ignore[assignment]
        _restore(socket, "socket", original_socket)
        _restore(socket, "create_connection", original_create_connection)
        import urllib.request

        original_urlopen = urllib.request.urlopen

        def blocked_urlopen(*_args, **_kwargs):
            raise PermissionError("network capability required")

        urllib.request.urlopen = blocked_urlopen  # type: ignore[assignment]
        _restore(urllib.request, "urlopen", original_urlopen)

    try:
        yield
    finally:
        for restore in reversed(restores):
            restore()


def _resolve_caller_module() -> str | None:
    stack = inspect.stack()
    for frame in stack[2:]:
        module = inspect.getmodule(frame.frame)
        if module and module.__name__ != __name__:
            return module.__name__
    return None


def _build_context(
    kernel: ResidentKernel,
    name: str,
    declaration: Dict[str, Any],
    *,
    caller_module: str | None,
    dry_run: bool,
) -> PluginContext:
    def _view_to_dict(view: object) -> Dict[str, Any]:
        fields = getattr(view, "__dataclass_fields__", {})
        return {field: getattr(view, field) for field in fields}

    governance = kernel.governance_view()
    embodiment = kernel.embodiment_view()
    posture = governance.posture_flags
    epoch_active = kernel.epoch_active()
    epoch_id = kernel.active_epoch_id()
    return PluginContext(
        plugin_name=name,
        allowed_postures=declaration["allowed_postures"],
        requires_epoch=declaration["requires_epoch"],
        capabilities=declaration["capabilities"],
        posture=posture,
        epoch_id=epoch_id,
        epoch_active=epoch_active,
        caller_module=caller_module,
        headless=is_headless(),
        dry_run=dry_run,
        governance=MappingProxyType(_view_to_dict(governance)),
        embodiment=MappingProxyType(_view_to_dict(embodiment)),
    )


def register_plugin(name: str, plugin: BasePlugin) -> None:
    """Register a plug-in instance."""
    declaration = _normalize_declaration(name, plugin)
    PLUGINS[name] = plugin
    PLUGIN_DECLARATIONS[name] = declaration


def load_plugins() -> None:
    """Load plug-ins from disk using importlib."""
    global PLUGINS, PLUGINS_INFO, PLUGIN_STATE, PLUGIN_DECLARATIONS, _LOADED_FILES
    PLUGINS = {}
    PLUGINS_INFO = {}
    PLUGIN_DECLARATIONS = {}
    plugins_dir = Path(os.getenv("GP_PLUGINS_DIR", "gp_plugins"))
    if not plugins_dir.exists():
        return
    _LOADED_FILES = list(plugins_dir.glob("*.py"))
    for fp in _LOADED_FILES:
        try:
            source_text = fp.read_text(encoding="utf-8")
        except Exception as e:  # pragma: no cover - read failures
            te.log_event("plugin_load_error", "load", str(e), fp.stem)
            continue
        if "sentientos.core" in source_text:
            te.log_event("plugin_invalid", "load", "forbidden sentientos.core import", fp.stem)
            continue
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
            except PluginDeclarationError as e:
                te.log_event("plugin_invalid", "register", str(e), fp.stem)
                continue
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
            PLUGIN_DECLARATIONS.pop(name, None)


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
    declaration = PLUGIN_DECLARATIONS.get(name, {})
    return {
        "id": name,
        "type": plug.plugin_type,
        "schema": plug.schema,
        "doc": PLUGINS_INFO.get(name, ""),
        "allowed_postures": declaration.get("allowed_postures"),
        "requires_epoch": declaration.get("requires_epoch"),
        "capabilities": declaration.get("capabilities"),
    }


def run_plugin(
    name: str,
    event: Dict[str, Any] | None = None,
    *,
    cause: str = "test",
    user: str = "plugin",
    kernel: ResidentKernel | None = None,
    dry_run: bool = False,
    caller_module: str | None = None,
) -> Dict[str, Any]:
    """Execute a plug-in and log via the trust engine."""
    plug = PLUGINS.get(name)
    if not plug:
        raise ValueError("Unknown plugin")
    if not PLUGIN_STATE.get(name, True):
        raise ValueError("Plugin disabled")

    declaration = PLUGIN_DECLARATIONS.get(name)
    if not declaration:
        raise PluginDeclarationError(f"{name} missing declaration")

    kernel = kernel or _KERNEL
    caller_module = caller_module or _resolve_caller_module()
    evt = MappingProxyType(dict(event or {}))

    if kernel is None:
        reason = "missing_kernel_context"
        PLUGIN_HEALTH[name] = {"status": "blocked", "reason": reason}
        te.log_event(
            "plugin_blocked",
            cause,
            reason,
            name,
            {"caller": caller_module, "capabilities": declaration.get("capabilities")},
        )
        rs.log_event(name, "blocked", cause, "kernel_missing", reason)
        return {"error": reason, "blocked": True}

    context = _build_context(
        kernel,
        name,
        declaration,
        caller_module=caller_module,
        dry_run=dry_run,
    )

    if context.posture not in context.allowed_postures:
        reason = f"posture_mismatch:{context.posture}"
        PLUGIN_HEALTH[name] = {"status": "blocked", "reason": reason}
        te.log_event(
            "plugin_blocked",
            cause,
            reason,
            name,
            {
                "posture": context.posture,
                "caller": caller_module,
                "capabilities": context.capabilities,
            },
        )
        rs.log_event(name, "blocked", cause, "posture_mismatch", reason)
        return {"error": reason, "blocked": True}

    if context.requires_epoch and not context.epoch_active and not dry_run:
        reason = "epoch_missing"
        PLUGIN_HEALTH[name] = {"status": "blocked", "reason": reason}
        te.log_event(
            "plugin_blocked",
            cause,
            reason,
            name,
            {
                "posture": context.posture,
                "epoch_id": context.epoch_id,
                "caller": caller_module,
                "capabilities": context.capabilities,
            },
        )
        rs.log_event(name, "blocked", cause, "epoch_missing", reason)
        return {"error": reason, "blocked": True}

    try:
        with _sandbox_capabilities(context.capabilities):
            result = plug.run(evt, context=context, dry_run=dry_run)
        PLUGIN_HEALTH[name] = {"status": "ok"}
        explanation = result.get("explanation", f"{name} executed")
        te.log_event(
            plug.plugin_type,
            cause,
            explanation,
            name,
            {
                "event": dict(evt),
                "result": result,
                "headless": context.headless,
                "dry_run": dry_run,
                "capabilities": context.capabilities,
                "posture": context.posture,
                "epoch_id": context.epoch_id,
                "caller": caller_module,
            },
        )
        rs.log_event(
            name,
            "action",
            cause,
            "executed",
            explanation,
            {
                "capabilities": context.capabilities,
                "posture": context.posture,
                "epoch_id": context.epoch_id,
                "caller": caller_module,
            },
        )
        try:
            raw_tags = evt.get("memory_tags") or evt.get("tags")
            if isinstance(raw_tags, (str, bytes)) or raw_tags is None:
                tag_list = [raw_tags] if isinstance(raw_tags, str) else []
            else:
                tag_list = list(raw_tags)
            summary = embodiment_digest.sanitize_action_summary(evt)
            embodiment_digest.record_embodiment_digest_entry(
                kernel=kernel,
                plugin_name=name,
                declared_capability=context.capabilities,
                posture=context.posture,
                epoch_id=context.epoch_id,
                action_summary=summary,
                memory_tags=tag_list,
                dry_run=bool(dry_run or context.headless or result.get("simulated")),
            )
        except Exception as exc:  # pragma: no cover - best effort logging
            te.log_event(
                "embodiment_digest_error",
                cause,
                str(exc),
                name,
                {"epoch_id": context.epoch_id, "posture": context.posture},
            )
        return result
    except PermissionError as e:
        err = str(e)
        PLUGIN_HEALTH[name] = {"status": "blocked", "reason": err}
        te.log_event(
            "plugin_blocked",
            cause,
            err,
            name,
            {
                "capabilities": context.capabilities,
                "posture": context.posture,
                "epoch_id": context.epoch_id,
                "caller": caller_module,
            },
        )
        rs.log_event(name, "blocked", cause, "capability_violation", err)
        return {"error": err, "blocked": True}
    except Exception as e:  # pragma: no cover - rare
        err = str(e)
        PLUGIN_HEALTH[name] = {"status": "error", "error": err}
        te.log_event(
            "plugin_error",
            "run_exception",
            err,
            name,
            {
                "capabilities": context.capabilities,
                "posture": context.posture,
                "epoch_id": context.epoch_id,
                "caller": caller_module,
            },
        )
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


def test_plugin(
    name: str,
    *,
    kernel: ResidentKernel | None = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Run a plug-in with empty event for testing."""
    return run_plugin(name, {"test": True}, cause="plugin_test", kernel=kernel, dry_run=dry_run)


def model_trigger(
    name: str,
    event: Dict[str, Any] | None = None,
    *,
    reason: str = "model_request",
    user: str = "model",
    kernel: ResidentKernel | None = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Trigger a plug-in from a model with trust logging."""
    return run_plugin(name, event or {}, cause=reason, user=user, kernel=kernel, dry_run=dry_run)


load_plugins()
