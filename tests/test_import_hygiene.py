from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_PREFIXES = ("agents.forms",)
REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (REPO_ROOT / "sentientos", REPO_ROOT / "cli")


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute) and isinstance(test.value, ast.Name):
        return test.value.id == "typing" and test.attr == "TYPE_CHECKING"
    return False


def _matches_forbidden(name: str) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for prefix in FORBIDDEN_PREFIXES)


def _find_forbidden_top_level_imports(path: Path) -> list[str]:
    offenders: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            continue
        if isinstance(node, ast.ImportFrom):
            if node.module and _matches_forbidden(node.module):
                offenders.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_forbidden(alias.name):
                    offenders.append(alias.name)
    return offenders


def test_forbidden_optional_imports_are_not_top_level() -> None:
    offenders: dict[str, list[str]] = {}
    for root in SCAN_ROOTS:
        for path in root.rglob("*.py"):
            if "tests" in path.parts or "agents" in path.parts:
                continue
            found = _find_forbidden_top_level_imports(path)
            if found:
                offenders[path.relative_to(REPO_ROOT).as_posix()] = found
    assert not offenders, f"top-level optional imports found: {offenders}"
