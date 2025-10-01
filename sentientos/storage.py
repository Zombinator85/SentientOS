from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

__all__ = [
    "ensure_mounts",
    "get_data_root",
    "get_state_file",
]

_DEFAULT_MOUNTS = ("vow", "glow", "pulse", "daemon")
_DATA_ROOT_ENV = "SENTIENTOS_DATA_DIR"


def get_data_root() -> Path:
    """Return the directory used for SentientOS runtime data.

    The directory can be customised through the ``SENTIENTOS_DATA_DIR``
    environment variable. When unset, a ``sentientos_data`` folder in the
    current working directory is used instead. The directory is created lazily
    when first requested.
    """

    candidate = os.environ.get(_DATA_ROOT_ENV)
    base = Path(candidate) if candidate else Path.cwd() / "sentientos_data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def ensure_mounts() -> Dict[str, Path]:
    """Ensure the default runtime mounts exist and return their paths."""

    root = get_data_root()
    mounts: Dict[str, Path] = {}
    for name in _DEFAULT_MOUNTS:
        mount = root / name
        mount.mkdir(parents=True, exist_ok=True)
        mounts[name] = mount
    return mounts


def get_state_file(name: str) -> Path:
    """Return the path to a state file stored within the data directory."""

    return get_data_root() / name
