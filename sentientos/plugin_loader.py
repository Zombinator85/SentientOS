from __future__ import annotations

"""Simple plugin loader for SentientOS with live reloading."""
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import importlib
import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Iterable, Protocol, TYPE_CHECKING


class ObserverProto(Protocol):
    def schedule(
        self, handler: "FileSystemEventHandler", path: str, recursive: bool = False
    ) -> object:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def join(self, timeout: float | None = None) -> None:
        ...

from gui_stub import CathedralGUI


class FileSystemEvent:
    def __init__(self, src_path: str) -> None:
        self.src_path = src_path


class FileSystemEventHandler:
    def on_modified(self, event: "FileSystemEvent") -> None:  # pragma: no cover - stub
        pass

    def on_created(self, event: "FileSystemEvent") -> None:  # pragma: no cover - stub
        pass

Observer: type[ObserverProto] | None = None

if not TYPE_CHECKING:
    try:  # optional watchdog dependency
        from watchdog.events import FileSystemEvent as WDFileSystemEvent
        from watchdog.events import FileSystemEventHandler as WDHandler
        from watchdog.observers import Observer as WDObserver

        FileSystemEvent = WDFileSystemEvent  # type: ignore[assignment]
        FileSystemEventHandler = WDHandler  # type: ignore[assignment]
        Observer = WDObserver  # type: ignore[assignment]
    except Exception:  # pragma: no cover - optional dependency
        Observer = None

import argparse
from importlib.metadata import entry_points


class PluginBus:
    """Minimal bus collecting registered plugins."""

    def __init__(self) -> None:
        self.plugins: dict[str, ModuleType] = {}

    def register(self, name: str, plugin: ModuleType) -> None:
        """Register a plugin under ``name``."""
        self.plugins[name] = plugin


class PluginLoader:
    """Watch a plugins directory and load modules on changes."""

    def __init__(self, gui: "CathedralGUI", directory: str = "plugins") -> None:
        self.gui = gui
        self.directory = Path(directory)
        self.bus = PluginBus()
        self.modules: dict[str, ModuleType] = {}
        self.errors: dict[str, str] = {}
        self.trusted_only = True
        self.observer: ObserverProto | None = None
        self._start()

    # watcher setup
    def _start(self) -> None:
        self.directory.mkdir(exist_ok=True)
        self._load_existing()
        if Observer is None:
            return

        class Handler(FileSystemEventHandler):
            def __init__(self, outer: "PluginLoader") -> None:
                self.outer = outer

            def on_modified(self, event: FileSystemEvent) -> None:
                self.outer._handle(event)

            def on_created(self, event: FileSystemEvent) -> None:
                self.outer._handle(event)

        self.observer = Observer()
        self.observer.schedule(Handler(self), str(self.directory), recursive=False)
        self.observer.start()

    def stop(self) -> None:
        if self.observer:
            self.observer.stop()
            self.observer.join()

    def _handle(self, event: FileSystemEvent) -> None:
        path = Path(event.src_path)
        if path.suffix == ".py":
            self._load_plugin(path.stem)

    def _load_existing(self) -> None:
        for fp in self.directory.glob("*.py"):
            self._load_plugin(fp.stem)

    def _load_plugin(self, name: str) -> None:
        mod_name = f"{self.directory.name}.{name}"
        try:
            if mod_name in sys.modules:
                mod = importlib.reload(sys.modules[mod_name])
            else:
                spec = importlib.util.spec_from_file_location(mod_name, self.directory / f"{name}.py")
                if not spec or not spec.loader:
                    raise ImportError(mod_name)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)

            if self.trusted_only and not getattr(mod, "TRUSTED", True):
                self.errors[name] = "untrusted"
                return

            reg = getattr(mod, "register", None)
            if callable(reg):
                reg(self.gui)
                self.modules[name] = mod
                self.errors.pop(name, None)
            else:
                self.errors[name] = "missing register()"
        except Exception as e:  # pragma: no cover - load failures
            self.errors[name] = str(e)

        self._refresh()

    def _refresh(self) -> None:
        if hasattr(self.gui, "update"):
            try:
                getattr(self.gui, "update")()
            except Exception:
                pass
        elif hasattr(self.gui, "refresh"):
            try:
                getattr(self.gui, "refresh")()
            except Exception:
                pass

    def active_plugins(self) -> list[str]:
        return list(self.modules.keys())

    def error_log(self) -> dict[str, str]:
        return dict(self.errors)

    def set_trusted_only(self, value: bool) -> None:
        self.trusted_only = value
        self._load_existing()


class PluginPanel:
    """Simple GUI panel showing plugin status."""

    def __init__(self, loader: PluginLoader) -> None:
        self.loader = loader
        self.gui = loader.gui

        self._mode: str | None = None
        self.control: object | None = None
        try:  # prefer Flet if available
            import flet as ft
            self._mode = "flet"
            self._ft = ft
            self.plugin_list = ft.Column()
            self.error_list = ft.Column()
            self.toggle = ft.Checkbox(label="Trusted only", value=True)
            setattr(self.toggle, "on_change", self._toggle)
            self.control = ft.Column([
                ft.Text("Plugins"),
                self.plugin_list,
                ft.Text("Errors"),
                self.error_list,
                self.toggle,
            ])
        except Exception:
            try:
                from PySide6.QtWidgets import (
                    QWidget,
                    QVBoxLayout,
                    QListWidget,
                    QLabel,
                    QCheckBox,
                )

                self._mode = "pyside"
                self.widget = QWidget()
                layout = QVBoxLayout(self.widget)
                layout.addWidget(QLabel("Plugins"))
                self.plugin_list = QListWidget()
                layout.addWidget(self.plugin_list)
                layout.addWidget(QLabel("Errors"))
                self.error_list = QListWidget()
                layout.addWidget(self.error_list)
                self.toggle = QCheckBox("Trusted only")
                self.toggle.setChecked(True)
                self.toggle.stateChanged.connect(self._toggle)
                layout.addWidget(self.toggle)
                self.control = self.widget
            except Exception:
                self._mode = "none"
        self.refresh()

    def _toggle(self, *_: object) -> None:
        if self._mode == "flet":
            self.loader.set_trusted_only(self.toggle.value)
        elif self._mode == "pyside":
            self.loader.set_trusted_only(self.toggle.isChecked())
        else:
            self.loader.set_trusted_only(not self.loader.trusted_only)
        self.refresh()

    def refresh(self) -> None:
        active = self.loader.active_plugins()
        errors = self.loader.error_log()
        if self._mode == "flet":
            self.plugin_list.controls = [self._ft.Text(n) for n in active]
            self.error_list.controls = [self._ft.Text(f"{k}: {v}") for k, v in errors.items()]
        elif self._mode == "pyside":
            self.plugin_list.clear()
            self.plugin_list.addItems(active)
            self.error_list.clear()
            self.error_list.addItems([f"{k}: {v}" for k, v in errors.items()])
        self.loader._refresh()


def load_plugins(bus: PluginBus, *, load: bool = True) -> Iterable[str]:
    """Locate plugins and optionally load them."""
    eps = entry_points(group="sentientos.plugins")
    names = [ep.name for ep in eps]
    if not load:
        return names
    for ep in eps:
        try:
            mod = ep.load()
            reg = getattr(mod, "register", None)
            if callable(reg):
                reg(bus)
        except Exception:
            # Ignore load failures
            continue
    return names


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SentientOS plugin loader")
    parser.add_argument("--list", action="store_true", help="List available plugins")
    args = parser.parse_args(argv)

    bus = PluginBus()
    names = load_plugins(bus, load=not args.list)

    if args.list:
        for name in names:
            print(name)
        return

    gui = CathedralGUI()
    loader = PluginLoader(gui)
    panel = PluginPanel(loader)
    gui.add_panel(panel.control)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        loader.stop()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
