"""Statically verify the actuator's immutable executable snapshot boundary."""

from __future__ import annotations

import ast
from pathlib import Path


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} function")
    return matches[0]


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        if isinstance(item.func, ast.Name):
            names.add(item.func.id)
        elif isinstance(item.func, ast.Attribute):
            names.add(item.func.attr)
    return names


def verify(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    snapshot = _function(tree, "_snapshot_executable")
    snapshot_calls = _call_names(snapshot)
    required = {"_open_canonical_executable", "fstat", "read", "write", "memfd_create", "fcntl"}
    if not required <= snapshot_calls:
        raise ValueError("snapshot lacks open, bounded copy, stability, or sealing primitives")
    source = ast.unparse(snapshot)
    for token in (
        "MAX_EXECUTABLE_SNAPSHOT_BYTES", "_source_stability(before)",
        "_source_stability(after)", "F_ADD_SEALS", "F_GET_SEALS", "_ELF_MAGIC",
    ):
        if token not in source:
            raise ValueError(f"snapshot invariant missing: {token}")

    run_shell = _function(tree, "run_shell")
    statements = [ast.unparse(statement) for statement in run_shell.body]
    snapshot_index = next((i for i, value in enumerate(statements) if "_snapshot_executable" in value), -1)
    authorization_index = next((i for i, value in enumerate(statements) if "_authorize_effect" in value), -1)
    if snapshot_index < 0 or authorization_index < 0 or snapshot_index >= authorization_index:
        raise ValueError("executable snapshot must be bound before authorization")
    calls = [item for item in ast.walk(run_shell) if isinstance(item, ast.Call)]
    process_calls = [item for item in calls if isinstance(item.func, ast.Attribute) and item.func.attr == "run"]
    if len(process_calls) != 1:
        raise ValueError("run_shell must have one subprocess boundary")
    keywords = {item.arg: item.value for item in process_calls[0].keywords}
    executable = keywords.get("executable")
    if executable is None or ast.unparse(executable) != "snapshot.execution_path":
        raise ValueError("process executable is not snapshot-derived")
    pass_fds = keywords.get("pass_fds")
    if pass_fds is None or ast.unparse(pass_fds) != "(snapshot.fd,)":
        raise ValueError("only the snapshot descriptor may cross process creation")
    if any(name in _call_names(run_shell) for name in ("fork", "execve")):
        raise ValueError("raw fork/exec bridge forbidden")
    if "preexec_fn" in keywords:
        raise ValueError("preexec_fn forbidden")


def main() -> int:
    verify(Path(__file__).resolve().parents[1] / "api" / "actuator.py")
    print("actuator_executable_object_custody_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
