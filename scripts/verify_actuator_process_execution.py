from __future__ import annotations

"""Mechanical guard for the sole built-in actuator process-creation surface."""

import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "api" / "actuator.py"
FORBIDDEN_TEXT = ("os.system", "/bin/sh", "bash -c", "cmd /c", "powershell -command")


def verify() -> list[str]:
    text = SOURCE.read_text(encoding="utf-8")
    errors = [f"forbidden bridge: {token}" for token in FORBIDDEN_TEXT if token.lower() in text.lower()]
    tree = ast.parse(text)
    custody = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_authorized_shell_argv"),
        None,
    )
    if custody is None:
        errors.append("structured shell custody function missing")
    else:
        custody_text = ast.get_source_segment(text, custody) or ""
        for required in ('WHITELIST.get("shell", [])', '"alias"', '"executable"', '"arguments"', '_safe_path'):
            if required not in custody_text:
                errors.append(f"structured shell custody missing: {required}")
        for forbidden in ("fnmatch", "fullmatch", "shutil.which", "PATH"):
            if forbidden in custody_text:
                errors.append(f"ambient or broad shell authorization found: {forbidden}")
    process_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    if len(process_calls) != 1:
        errors.append(f"expected one subprocess call, found {len(process_calls)}")
    for call in process_calls:
        shell = next((kw.value for kw in call.keywords if kw.arg == "shell"), None)
        if not isinstance(shell, ast.Constant) or shell.value is not False:
            errors.append("subprocess call must specify shell=False")
        if not call.args or not isinstance(call.args[0], ast.Name) or call.args[0].id != "authorized_argv":
            errors.append("subprocess must receive authorized_argv")
    policy = SOURCE.parents[0].parent / "config" / "act_whitelist.yml"
    if "shell: []" not in policy.read_text(encoding="utf-8"):
        errors.append("shipped shell policy must be empty")
    return errors


def main() -> int:
    errors = verify()
    if errors:
        print("actuator_process_execution_verifier: failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("actuator_process_execution_verifier: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
