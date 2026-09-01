"""Narrow static authority boundary for production conversations."""
from __future__ import annotations

import ast
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "sentientos/conversation_session.py", root / "sentientos/chat_service.py"]
    forbidden = {"create_chat_completion", "generate_governed", "requests", "httpx", "openai", "urllib"}
    findings: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in node.names]
                findings.extend(f"{path.name}:forbidden_import:{name}" for name in names if name in forbidden)
            if path.name == "conversation_session.py" and isinstance(node, ast.Attribute) and node.attr in {"generate", "invoke"}:
                findings.append(f"{path.name}:inference_call:{node.attr}")
    chat = paths[1].read_text(encoding="utf-8")
    if "GovernedLocalModelInvoker" not in chat or "self.invoker.invoke" not in chat:
        findings.append("chat_service:governed_invoker_missing")
    context = paths[0].read_text(encoding="utf-8")
    if "[RETRIEVED_MEMORY_DATA_UNTRUSTED]" not in context or "MEMORY_DATA:" not in context:
        findings.append("conversation_session:memory_provenance_missing")
    if findings:
        print("persistent_conversation_authority_blocked", *findings, sep="\n")
        return 1
    print("persistent_conversation_authority_verified")
    return 0


if __name__ == "__main__": raise SystemExit(main())
