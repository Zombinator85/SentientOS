"""Legacy test quarantine policy helpers."""

from __future__ import annotations

from collections.abc import Mapping, Set
from pathlib import PurePosixPath

LEGACY_SKIP_REASON = "legacy test disabled: run with -m legacy"


def legacy_marker_enabled(markexpr: str | None) -> bool:
    if not markexpr:
        return False
    return "legacy" in markexpr


def _is_phase_test_path(path_str: str) -> bool:
    normalized = path_str.replace("\\", "/")
    name = PurePosixPath(normalized).name
    return name.startswith("test_phase") and name.endswith(".py")


def is_legacy_candidate(
    *,
    module_name: str,
    path_str: str,
    test_name: str,
    keywords: Mapping[str, object],
    allowed_modules: Set[str],
) -> bool:
    if test_name == "test_placeholder":
        return False
    if test_name.startswith("test_emotion_pump"):
        return False
    if _is_phase_test_path(path_str):
        return False
    if "tests/e2e/" in path_str:
        return False
    if "tests/consciousness/" in path_str:
        return False
    if module_name in allowed_modules:
        return False
    if module_name.startswith("tests.integrity."):
        return False
    if "always_on_integrity" in keywords:
        return False
    if "no_legacy_skip" in keywords:
        return False
    return True


__all__ = ["LEGACY_SKIP_REASON", "is_legacy_candidate", "legacy_marker_enabled"]
