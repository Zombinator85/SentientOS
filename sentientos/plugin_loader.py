from __future__ import annotations

"""Simple plugin loader for SentientOS."""

import argparse
from importlib.metadata import entry_points
from typing import Any, Iterable


class PluginBus:
    """Minimal bus collecting registered plugins."""

    def __init__(self) -> None:
        self.plugins: dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        """Register a plugin under ``name``."""
        self.plugins[name] = plugin


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


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
