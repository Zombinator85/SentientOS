"""Structural fail-closed check for the runtime supervisor authority boundary."""
from __future__ import annotations
import ast
from pathlib import Path

FILES = (Path("sentientos/runtime/supervisor.py"), Path("sentientos/runtime/services.py"))
FORBIDDEN_IMPORTS = {"requests", "httpx", "openai", "anthropic", "boto3"}
FORBIDDEN_CALLS = {"system", "popen", "eval", "exec", "assemble_prompt", "invoke_provider"}

def verify(root: Path = Path.cwd()) -> list[str]:
    findings: list[str] = []
    for relative in FILES:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [x.name.split(".")[0] for x in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
                if FORBIDDEN_IMPORTS.intersection(names): findings.append(f"{relative}:forbidden_import")
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
                if name in FORBIDDEN_CALLS: findings.append(f"{relative}:forbidden_call:{name}")
                if any(x.arg == "shell" and isinstance(x.value, ast.Constant) and x.value.value is True for x in node.keywords): findings.append(f"{relative}:shell_true")
    return findings

def main() -> int:
    findings = verify()
    print("runtime_supervisor_authority_verified" if not findings else "\n".join(findings))
    return 0 if not findings else 1
if __name__ == "__main__": raise SystemExit(main())
