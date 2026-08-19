"""Static verification of the metadata-only model selection boundary."""
from __future__ import annotations

import ast
from pathlib import Path


def main() -> int:
    planner = Path("sentientos/local_model_selection.py").read_text(encoding="utf-8")
    tree = ast.parse(planner)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
    forbidden_imports = {"requests", "httpx", "huggingface_hub", "subprocess", "gpu_autosetup", "llama_cpp"}
    findings = sorted(name for name in imports if name.split(".")[0] in forbidden_imports)
    forbidden_text = ("pip install", "local_model_commissioning", "\"cuda\" in", "'cuda' in")
    findings.extend(token for token in forbidden_text if token in planner.lower())
    dry_run = Path("installer/dry_run.py").read_text(encoding="utf-8")
    if "models[0]" in dry_run: findings.append("dry_run models[0]")
    for required in ("UNKNOWN", "unresolved", "manifest_accelerator_backend_unspecified"):
        if required not in planner: findings.append(f"missing {required}")
    print("local_model_selection_boundary_verified" if not findings else "boundary_failed: " + ", ".join(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
