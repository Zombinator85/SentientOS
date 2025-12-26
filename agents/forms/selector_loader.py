"""Utilities for loading SSA selector maps."""
from __future__ import annotations

from typing import Dict

from sentientos.optional_deps import optional_import

yaml = optional_import("pyyaml", feature="ssa_selector_loader")


def load_selectors(path: str) -> Dict[str, Dict[str, object]]:
    """Load a YAML selector map from disk."""
    if yaml is None:
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def get_page(page_name: str, selectors: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    """Deterministically fetch a page structure from the selector map."""
    return selectors.get(page_name, {}) if selectors else {}
