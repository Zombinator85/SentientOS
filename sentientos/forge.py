"""Thin shim for Forge CLI entrypoint."""

from __future__ import annotations

from collections.abc import Sequence

from sentientos.forge_cli.main import main as _forge_main


def main(argv: Sequence[str] | None = None) -> int:
    return _forge_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
