"""Statically verify descriptor-bound command working-directory custody."""

from __future__ import annotations

import ast
from pathlib import Path


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} function")
    return matches[0]


def verify(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    source = path.read_text(encoding="utf-8")
    lexical = ast.unparse(_function(tree, "_command_cwd_components"))
    for token in ("isinstance(cwd, str)", "'\\x00' in cwd", "is_absolute()", "'..' in components"):
        if token not in lexical:
            raise ValueError(f"cwd lexical invariant missing: {token}")
    if ".resolve(" in lexical:
        raise ValueError("cwd lexical authority must not resolve pathnames")

    opener = ast.unparse(_function(tree, "_open_command_cwd"))
    for token in (
        "_open_sandbox_root(create=False)", "_open_directory_component(directory_fd, component, create=False)",
        "os.close(directory_fd)", "_CommandCwdHandle(directory_fd, reporting_path)",
    ):
        if token not in opener:
            raise ValueError(f"cwd descriptor invariant missing: {token}")
    component_opener = ast.unparse(_function(tree, "_open_directory_component"))
    for token in ("os.O_DIRECTORY", "os.O_NOFOLLOW", "dir_fd=parent_fd"):
        if token not in component_opener:
            raise ValueError(f"descriptor walk primitive missing: {token}")

    run_shell = _function(tree, "run_shell")
    rendered = ast.unparse(run_shell)
    bind_index = rendered.find("cwd_handle = _open_command_cwd(cwd_components)")
    authorize_index = rendered.find("_authorize_effect()")
    process_index = rendered.find("subprocess.run(")
    if min(bind_index, authorize_index, process_index) < 0 or not bind_index < authorize_index < process_index:
        raise ValueError("cwd object must be held before authorization and process construction")
    calls = [node for node in ast.walk(run_shell) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run"]
    if len(calls) != 1:
        raise ValueError("run_shell must contain one subprocess call")
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    if ast.unparse(keywords["cwd"]) != "cwd_handle.execution_path":
        raise ValueError("subprocess cwd must derive only from the held directory fd")
    if ast.unparse(keywords["pass_fds"]) != "(snapshot.fd, cwd_handle.fd)":
        raise ValueError("process descriptor tuple must contain exactly the two custody fds")
    forbidden_source = ("preexec_fn", "os.fork(", "os.chdir(", "cwd=str(", "shell=True")
    if any(token in rendered for token in forbidden_source):
        raise ValueError("forbidden cwd fallback or child/parent process bridge")
    if "def _open_sandbox_root(*, create: bool = True)" not in source:
        raise ValueError("sandbox root opener lacks explicit existing-only mode")


def main() -> int:
    verify(Path(__file__).resolve().parents[1] / "api" / "actuator.py")
    print("actuator_cwd_object_custody_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
