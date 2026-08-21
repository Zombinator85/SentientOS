"""Static zero-effect boundary verifier for runtime provisioning."""
from __future__ import annotations
import ast
from pathlib import Path

FORBIDDEN = {"subprocess", "requests", "httpx", "pip", "gpu_autosetup", "llama_cpp", "torch", "local_model_commissioning"}

REQUIRED_SOURCE_FACTS = (
    'CATALOG_SCHEMA_VERSION_V2 = "sentientos.local_runtime_catalog:v2"',
    "supported_python_versions", "python_tag", "abi_tag", "platform_tag", "backend_variant",
    "wheel_tag_metadata_mismatch", "MANYLINUX_RE", "glibc_too_old", "libc_unknown",
    "MACOS_RE", "macos_version_unknown", "macos_version_too_old",
)

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
    source = paths[0].read_text(encoding="utf-8")
    for fact in REQUIRED_SOURCE_FACTS:
        if fact not in source:
            errors.append(f"{paths[0]}: missing contract fact {fact}")
    if 'abi != "none" and abi != env.python_abi' not in source:
        errors.append(f"{paths[0]}: py3-none ABI boundary is not explicit")
    if "production_runtime_catalog_ready = true" in source.lower():
        errors.append(f"{paths[0]}: production runtime entry introduced")
    print("local_runtime_provisioning_verified" if not errors else "\n".join(errors))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
