from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_cli_path = Path(__file__).resolve().parent.parent / "privilege_lint.py"
_spec = importlib.util.spec_from_file_location("_privilege_lint_cli", _cli_path)
if _spec is None or _spec.loader is None:
    raise ImportError("Failed to load privilege_lint CLI module")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

globals().update({k: getattr(_module, k) for k in dir(_module) if not k.startswith("_")})
