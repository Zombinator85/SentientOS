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
