"""Runtime patches applied when the interpreter starts.

Adds optional ``append`` support to :class:`pathlib.Path` write helpers so tests
can accumulate content without reimplementing file handling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar

_PathT = TypeVar("_PathT", bound=Path)


def _patch_write_text(path_cls: type[_PathT]) -> None:
    original: Callable[[Path, str, str | None, str | None], int] = path_cls.write_text

    def write_text(
        self: _PathT,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        append: bool = False,
    ) -> int:  # type: ignore[override]
        if append:
            # Mirror pathlib.Path.write_text return type by returning characters written.
            with self.open("a", encoding=encoding, errors=errors) as handle:
                return handle.write(data)
        return original(self, data, encoding=encoding, errors=errors)

    path_cls.write_text = write_text  # type: ignore[assignment]


def _patch_write_bytes(path_cls: type[_PathT]) -> None:
    original: Callable[[Path, bytes], int] = path_cls.write_bytes

    def write_bytes(self: _PathT, data: bytes, append: bool = False) -> int:  # type: ignore[override]
        if append:
            with self.open("ab") as handle:
                return handle.write(data)
        return original(self, data)

    path_cls.write_bytes = write_bytes  # type: ignore[assignment]


_patch_write_text(Path)
_patch_write_bytes(Path)
