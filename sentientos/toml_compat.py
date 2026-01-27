from __future__ import annotations

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:
    import tomli as tomllib  # py<3.11

__all__ = ["tomllib"]
