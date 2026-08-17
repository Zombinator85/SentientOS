"""Verify the narrow actuator subprocess environment-custody boundary."""

from __future__ import annotations

import ast
from pathlib import Path


def _run_shell_call(tree: ast.Module) -> ast.Call:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_shell":
            calls = [
                item
                for item in ast.walk(node)
                if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute)
                and isinstance(item.func.value, ast.Name)
                and item.func.value.id == "subprocess"
                and item.func.attr == "run"
            ]
            if len(calls) == 1:
                return calls[0]
    raise ValueError("run_shell must contain exactly one subprocess.run call")


def verify(path: Path) -> None:
    call = _run_shell_call(ast.parse(path.read_text(encoding="utf-8")))
    if any(keyword.arg is None for keyword in call.keywords):
        raise ValueError("generic subprocess keyword expansion is forbidden")
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    required = {"env", "stdin", "close_fds", "shell"}
    if not required <= keywords.keys():
        raise ValueError("subprocess call lacks explicit environment custody controls")
    if not isinstance(keywords["env"], ast.Dict) or keywords["env"].keys:
        raise ValueError("child environment must be a fresh empty mapping")
    if not (
        isinstance(keywords["stdin"], ast.Attribute)
        and isinstance(keywords["stdin"].value, ast.Name)
        and keywords["stdin"].value.id == "subprocess"
        and keywords["stdin"].attr == "DEVNULL"
    ):
        raise ValueError("child stdin must be subprocess.DEVNULL")
    for name, expected in (("close_fds", True), ("shell", False)):
        value = keywords[name]
        if not isinstance(value, ast.Constant) or value.value is not expected:
            raise ValueError(f"{name} must be {expected!r}")
    forbidden = {"startupinfo", "creationflags"}
    if forbidden & keywords.keys():
        raise ValueError("forbidden subprocess authority control present")
    executable = keywords.get("executable")
    if not (
        isinstance(executable, ast.Attribute)
        and isinstance(executable.value, ast.Name)
        and executable.value.id == "snapshot"
        and executable.attr == "execution_path"
    ):
        raise ValueError("executable must be the internally owned snapshot path")
    pass_fds = keywords.get("pass_fds")
    if not (
        isinstance(pass_fds, ast.Tuple)
        and len(pass_fds.elts) == 1
        and isinstance(pass_fds.elts[0], ast.Attribute)
        and isinstance(pass_fds.elts[0].value, ast.Name)
        and pass_fds.elts[0].value.id == "snapshot"
        and pass_fds.elts[0].attr == "fd"
    ):
        raise ValueError("pass_fds must contain only the internally owned snapshot descriptor")


def main() -> int:
    verify(Path(__file__).resolve().parents[1] / "api" / "actuator.py")
    print("actuator_command_environment_custody_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
