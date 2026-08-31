"""AST boundary verifier for the model-byte acquisition organ."""
from __future__ import annotations
import ast
import json
from pathlib import Path

FORBIDDEN_IMPORTS = {"llama_cpp", "subprocess", "pip", "requests", "httpx", "sentientos.local_runtime_installation"}
FORBIDDEN_CALLS = {"Llama", "create_chat_completion", "create_completion", "run", "Popen"}

def main() -> int:
    paths = (Path("sentientos/local_model_artifact_acquisition.py"), Path("scripts/local_model_artifact_acquisition.py"))
    findings: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(any(name == denied or name.startswith(denied + ".") for denied in FORBIDDEN_IMPORTS) for name in names):
                    findings.append(f"{path}:forbidden_import")
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
                if name in FORBIDDEN_CALLS: findings.append(f"{path}:forbidden_call:{name}")
    print(json.dumps({"status": "local_model_artifact_acquisition_boundary_ready" if not findings else "blocked",
                      "findings": findings}, sort_keys=True))
    return 0 if not findings else 1

if __name__ == "__main__": raise SystemExit(main())
