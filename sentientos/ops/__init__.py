from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None, *, prog: str = "python -m sentientos.ops") -> int:
    from .__main__ import main as _main

    return int(_main(argv, prog=prog))


__all__ = ["main"]
