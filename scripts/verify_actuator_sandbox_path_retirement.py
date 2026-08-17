from __future__ import annotations

"""Verify that command argument policy grants only finite, exact string authority."""

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "api" / "actuator.py"
PATH_SLOT_SPELLINGS = {"sandbox_path", "sandbox-path", "sandboxPath", "path", "filesystem_path", "file_path"}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} function")
    return matches[0]


def verify(path: Path = SOURCE) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    authorization = _function(tree, "_authorized_shell_argv")
    rendered = ast.unparse(authorization)
    compared_slot_types = {
        comparator.value
        for node in ast.walk(authorization)
        if isinstance(node, ast.Compare)
        for comparator in node.comparators
        if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str)
        and isinstance(node.left, ast.Name) and node.left.id == "slot_type"
    }
    if compared_slot_types != {"literal", "one_of"}:
        raise ValueError(f"argument slot authority must be exactly literal and one_of: {sorted(compared_slot_types)}")
    if PATH_SLOT_SPELLINGS & compared_slot_types:
        raise ValueError("generic path argument slot is supported")
    if "_safe_path" in rendered:
        raise ValueError("command argument authorization calls _safe_path")
    if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_safe_path" for node in tree.body):
        raise ValueError("dead generic _safe_path helper remains")
    if "unsupported argument slot" not in rendered:
        raise ValueError("unknown argument slot types do not fail closed generically")

    run_shell = _function(tree, "run_shell")
    process_calls = [
        node for node in ast.walk(run_shell)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"
        and node.func.attr == "run"
    ]
    if len(process_calls) != 1:
        raise ValueError("run_shell must contain exactly one subprocess boundary")
    keywords = {keyword.arg: keyword.value for keyword in process_calls[0].keywords}
    pass_fds = keywords.get("pass_fds")
    if pass_fds is None or ast.unparse(pass_fds) != "(snapshot.fd, cwd_handle.fd)":
        raise ValueError("internal descriptor tuple must be exactly executable snapshot plus cwd handle")


def main() -> int:
    verify()
    print("actuator_sandbox_path_retirement_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
