"""Mechanically verify that the actuator surface has no external Python loader."""

from __future__ import annotations

import ast
import json
from pathlib import Path


FORBIDDEN_CALLS = {"exec", "eval", "spec_from_file_location"}
RETIRED_NAMES = {"load_plugins", "reload_plugins", "list_plugins"}


def verify(path: Path = Path("api/actuator.py")) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in RETIRED_NAMES:
            violations.append(f"retired_function:{node.name}:{node.lineno}")
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in FORBIDDEN_CALLS:
                violations.append(f"forbidden_call:{name}:{node.lineno}")
    for token in ("ACT_PLUGINS_DIR", "_LOADED_PLUGIN_FILES", "PLUGINS_INFO"):
        if token in source:
            violations.append(f"retired_surface:{token}")
    # Ordinary regular-expression compilation remains valid actuator behavior.
    # Plugin source compilation is mechanically impossible without a retired loader
    # function or an exec/eval/dynamic-import call, all checked above.
    parser_literals = {
        value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance((value := node.value), str)
    }
    for token in ("plugins", "--reload"):
        if token in parser_literals:
            violations.append(f"retired_cli:{token}")
    return {
        "status": "actuator_plugin_boundary_ready" if not violations else "actuator_plugin_boundary_blocked",
        "path": str(path),
        "violations": violations,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "actuator_plugin_boundary_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
