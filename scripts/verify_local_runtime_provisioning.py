"""Static zero-effect boundary verifier for runtime provisioning."""
from __future__ import annotations
import ast
from pathlib import Path

FORBIDDEN = {"subprocess", "requests", "httpx", "pip", "gpu_autosetup", "llama_cpp", "torch", "local_model_commissioning"}

def main() -> int:
    paths = (Path("sentientos/local_runtime_provisioning.py"), Path("scripts/local_runtime_provisioning.py"))
    errors: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[-1]}
            else:
                continue
            for name in sorted(names & FORBIDDEN): errors.append(f"{path}: forbidden import {name}")
    print("local_runtime_provisioning_verified" if not errors else "\n".join(errors))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
