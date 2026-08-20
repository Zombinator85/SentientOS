"""Static guard for the metadata-only local execution-route contract."""
from __future__ import annotations

import ast
from pathlib import Path


def main() -> int:
    manifest_text = Path("hf_intake/manifest.py").read_text(encoding="utf-8")
    selector_path = Path("sentientos/local_model_selection.py")
    selector_text = selector_path.read_text(encoding="utf-8")
    tree = ast.parse(selector_text)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
               for alias in node.names}
    forbidden = {"llama_cpp", "subprocess", "gpu_autosetup"}
    checks = {
        "v2_routes_required": "execution_routes must be a non-empty list" in manifest_text,
        "v2_gpu_forbidden": "V2 requirements.gpu is ambiguous and forbidden" in manifest_text,
        "curator_route_custody": 'source.get("execution_routes")' in manifest_text,
        "no_forbidden_imports": not (imports & forbidden),
        "runtime_not_evaluated": '"runtime_availability_status": "not_evaluated"' in selector_text,
        "v1_gpu_ambiguity": "manifest_accelerator_backend_unspecified" in selector_text,
        "no_filename_route_inference": "artifact_path.name" not in selector_text and '"cuda" in' not in selector_text,
    }
    failed = [name for name, passed in checks.items() if not passed]
    print("local_model_execution_routes_verified" if not failed else "failed:" + ",".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
