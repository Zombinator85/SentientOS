from __future__ import annotations

import os
from pathlib import Path

LOG_DIR_ENV = "SENTIENTOS_LOG_DIR"


def resolve_log_dir() -> Path:
    """Resolve the configured base log directory without creating it."""
    return Path(os.getenv(LOG_DIR_ENV, "logs"))


def get_log_dir() -> Path:
    """Return the base directory for logs, creating it if needed."""
    log_dir = resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def resolve_log_path(name: str, env_var: str | None = None) -> Path:
    """Resolve a log file path without creating its parent directory.

    If *env_var* is provided and that environment variable is set,
    its value is used directly. Otherwise the path is relative to
    the configured log directory.
    """
    if env_var and env_var in os.environ:
        return Path(os.environ[env_var])
    return resolve_log_dir() / name


def get_log_path(name: str, env_var: str | None = None) -> Path:
    """Return a log file path, creating the configured log directory."""
    path = resolve_log_path(name, env_var)
    if not (env_var and env_var in os.environ):
        get_log_dir()
    return path
