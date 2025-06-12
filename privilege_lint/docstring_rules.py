from __future__ import annotations

import ast
from pathlib import Path


def _style_matches(doc: str, style: str) -> bool:
    lines = [l.strip() for l in doc.splitlines()]
    if style == "google":
        return any(l.startswith("Args:") for l in lines)
    if style == "numpy":
        return any(l == "Parameters" for l in lines)
    return True


def validate_docstrings(lines: list[str], path: Path, style: str) -> list[str]:
    """Return lint errors for docstrings."""
    try:
        tree = ast.parse("\n".join(lines))
    except Exception:
        return []

    issues: list[str] = []

    def check(node: ast.AST, name: str) -> None:
        doc = ast.get_docstring(node)  # type: ignore[arg-type]  # mypy: node narrowed
        lineno = getattr(node, "lineno", 1)
        if not doc:
            issues.append(f"{path}:{lineno} missing docstring")
        elif not _style_matches(doc, style):
            issues.append(f"{path}:{lineno} docstring not {style} style")



    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            check(node, node.name)
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_"):
                        check(sub, f"{node.name}.{sub.name}")

    return issues


def apply_fix_docstring_stub(path: Path, style: str) -> bool:
    """Insert TODO docstring stubs for missing public docstrings."""
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        tree = ast.parse("\n".join(lines))
    except Exception:
        return False

    inserts: list[tuple[int, str]] = []

    def stub(indent: int) -> str:
        return " " * indent + '"""TODO:"""'

    if not ast.get_docstring(tree):
        inserts.append((0, stub(0)))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            if not ast.get_docstring(node):
                line = node.body[0].lineno if node.body else node.lineno + 1
                indent = node.body[0].col_offset if node.body else node.col_offset + 4
                inserts.append((line - 1, stub(indent)))
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("_") and not ast.get_docstring(sub):
                        line = sub.body[0].lineno if sub.body else sub.lineno + 1
                        indent = sub.body[0].col_offset if sub.body else sub.col_offset + 4
                        inserts.append((line - 1, stub(indent)))

    if not inserts:
        return False

    for idx, text in sorted(inserts, reverse=True):
        lines.insert(idx, text)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
