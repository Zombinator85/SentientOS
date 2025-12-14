"""Utilities for loading SSA selector maps."""
from __future__ import annotations

from typing import Dict
import importlib
import importlib.util
import warnings

try:
    _yaml_spec = importlib.util.find_spec("yaml")
except ValueError:
    _yaml_spec = None
if _yaml_spec is not None:
    yaml = importlib.import_module("yaml")
else:
    yaml = None
    warnings.warn("optional dependency PyYAML missing; YAML configs will be ignored")


def load_selectors(path: str) -> Dict[str, Dict[str, object]]:
    """Load a YAML selector map from disk."""
    if yaml is None:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_page(page_name: str, selectors: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    """Deterministically fetch a page structure from the selector map."""
    return selectors.get(page_name, {}) if selectors else {}
