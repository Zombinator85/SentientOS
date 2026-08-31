"""AST authority-boundary verifier for production model commissioning."""
from __future__ import annotations

import ast
import json
from pathlib import Path


def main() -> int:
    findings: list[str] = []
    commissioning = ast.parse(Path("sentientos/local_model_production_commissioning.py").read_text())
    chat = ast.parse(Path("sentientos/chat_service.py").read_text())
    acquisition = ast.parse(Path("sentientos/local_model_artifact_acquisition.py").read_text())
    forbidden_imports = {"requests", "httpx", "urllib", "socket", "openai", "transformers"}
    for tree, label in ((commissioning, "commissioning"), (chat, "chat")):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name.split(".")[0] in forbidden_imports for alias in node.names): findings.append(label + "_remote_import")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in forbidden_imports: findings.append(label + "_remote_import")
    if any(isinstance(n, ast.Attribute) and n.attr == "create_chat_completion" for n in ast.walk(chat)):
        findings.append("chat_direct_backend_bypass")
    if any(isinstance(n, ast.Name) and n.id == "LocalModel" for n in ast.walk(acquisition)):
        findings.append("acquisition_model_loader_reference")
    calls = {n.func.id for n in ast.walk(commissioning) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    if "GovernedLocalModelInvoker" not in calls and "invoker_factory" not in calls: findings.append("governed_smoke_missing")
    payload = {"status": "local_model_production_commissioning_boundary_ready" if not findings else "blocked", "findings": findings}
    print(json.dumps(payload, sort_keys=True)); return 0 if not findings else 1


if __name__ == "__main__": raise SystemExit(main())
