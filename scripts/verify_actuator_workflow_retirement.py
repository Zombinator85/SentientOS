"""Statically verify the narrow executable-workflow retirement boundary."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _names(tree: ast.AST) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def verify() -> None:
    actuator = ast.parse((ROOT / "api" / "actuator.py").read_text(encoding="utf-8"))
    controller = ast.parse((ROOT / "workflow_controller.py").read_text(encoding="utf-8"))
    library = ast.parse((ROOT / "workflow_library.py").read_text(encoding="utf-8"))

    assert "WorkflowActuator" not in _names(actuator), "active WorkflowActuator remains"
    builtins = next(
        node for node in actuator.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "BUILTIN_ACTUATOR_TYPES"
    )
    assert isinstance(builtins.value, ast.Dict)
    keys = {key.value for key in builtins.value.keys if isinstance(key, ast.Constant)}
    assert "workflow" not in keys, "workflow remains a built-in actuator type"

    forbidden_names = {"ACTION_REGISTRY", "WORKFLOWS", "_resolve_callable", "_wrap_action"}
    assigned = {
        target.id
        for node in ast.walk(controller)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in ((node.targets if isinstance(node, ast.Assign) else [node.target]))
        if isinstance(target, ast.Name)
    }
    assert not (forbidden_names & (_names(controller) | assigned))
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name == "importlib" for alias in node.names) for node in ast.walk(controller))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "compile", "require_admin_banner", "require_lumos_approval"} for node in ast.walk(controller))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"import_module", "add_argument"} for node in ast.walk(controller))
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval", "compile"}
        for node in ast.walk(library)
    )


def main() -> int:
    verify()
    print("actuator workflow retirement verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
