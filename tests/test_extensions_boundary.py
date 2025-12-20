from __future__ import annotations

import ast
from pathlib import Path


CORE_DIR = Path("sentientos")


def test_core_does_not_import_extensions() -> None:
    """Core modules must not import from any extension package."""
    violations: list[str] = []
    for path in CORE_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("extensions"):
                        violations.append(f"{path}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("extensions"):
                    violations.append(f"{path}: imports from {node.module}")
    assert not violations, "Core must not depend on extensions:\n" + "\n".join(violations)
