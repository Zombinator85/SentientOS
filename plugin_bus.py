"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Async plug-in bus with live reload support."""

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from gui_stub import CathedralGUI

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # pragma: no cover - optional dependency
    Observer = None  # type: ignore[assignment]
    FileSystemEventHandler = object  # type: ignore[assignment]


class PluginBus:
    """Collect and hot-reload GUI plug-ins."""

    def __init__(self, gui: CathedralGUI, directory: str = "plugins") -> None:
        self.gui = gui
        self.directory = Path(directory)
        self.modules: dict[str, ModuleType] = {}
        self.directory.mkdir(exist_ok=True)
        self._observer: Observer | None = None

    def load(self, name: str) -> None:
        """Import or reload ``name`` and call ``register(gui)``."""
        fp = self.directory / f"{name}.py"
        mod_name = f"{self.directory.name}.{name}"
        parent_name = self.directory.name
        if parent_name not in sys.modules:
            pkg = ModuleType(parent_name)
            pkg.__path__ = [str(self.directory)]  # type: ignore[attr-defined]
            sys.modules[parent_name] = pkg
        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            spec = importlib.util.spec_from_file_location(mod_name, fp)
            if not spec or not spec.loader:
                raise ImportError(mod_name)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            reg = getattr(mod, "register", None)
            if callable(reg):
                reg(self.gui)
            self.modules[name] = mod
        except Exception:  # pragma: no cover - runtime load issues
            self.modules.pop(name, None)

        if hasattr(self.gui, "refresh_plugins"):
            try:
                getattr(self.gui, "refresh_plugins")()
            except Exception:  # pragma: no cover - GUI issues
                pass

    def load_all(self) -> None:
        for fp in self.directory.glob("*.py"):
            if fp.stem == "__init__":
                continue
            self.load(fp.stem)

    async def watch_plugins(self) -> None:
        """Watch the directory for changes until cancelled."""
        self.load_all()
        if Observer is None:
            while True:
                await asyncio.sleep(3600)

        loop = asyncio.get_running_loop()

        class Handler(FileSystemEventHandler):
            def on_modified(self, event) -> None:  # type: ignore[override]
                path = Path(event.src_path)
                if path.suffix == ".py":
                    loop.call_soon_threadsafe(self_outer.load, path.stem)

            def on_created(self, event) -> None:  # type: ignore[override]
                path = Path(event.src_path)
                if path.suffix == ".py":
                    loop.call_soon_threadsafe(self_outer.load, path.stem)

        self_outer = self
        self._observer = Observer()
        self._observer.schedule(Handler(), str(self.directory), recursive=False)
        self._observer.start()
        try:
            while True:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        finally:
            if self._observer is not None:
                self._observer.stop()
                self._observer.join()
                self._observer = None

