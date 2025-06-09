from __future__ import annotations

import ast
from pathlib import Path


def _func_has_hints(fn: ast.FunctionDef, fail_on_missing_return: bool) -> bool:
    for arg in list(fn.args.args) + list(fn.args.kwonlyargs):
        if arg.annotation is None:
            return False
    if fn.args.vararg and fn.args.vararg.annotation is None:
        return False
    if fn.args.kwarg and fn.args.kwarg.annotation is None:
        return False
    if fail_on_missing_return and fn.returns is None:
        return False
    return True


def validate_type_hints(
    lines: list[str],
    path: Path,
    *,
    exclude_private: bool,
    fail_on_missing_return: bool,
) -> list[str]:
    """Return type hint coverage issues for a file."""
    issues: list[str] = []
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return issues
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if exclude_private and node.name.startswith("_"):
                continue
            if not _func_has_hints(node, fail_on_missing_return):
                issues.append(f"{path}:{node.lineno} missing type hints in {node.name}")
        elif isinstance(node, ast.ClassDef):
            if exclude_private and node.name.startswith("_"):
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if exclude_private and item.name.startswith("_"):
                        continue
                    if not _func_has_hints(item, fail_on_missing_return):
                        issues.append(
                            f"{path}:{item.lineno} missing type hints in {node.name}.{item.name}"
                        )
    return issues
