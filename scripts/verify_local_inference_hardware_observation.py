"""Static verifier for the bounded local-inference observation boundary."""
from __future__ import annotations

import ast
from pathlib import Path


TARGETS = (
    Path("sentientos/host_collectors.py"),
    Path("sentientos/host_inventory.py"),
    Path("sentientos/local_model_selection.py"),
    Path("scripts/local_inference_hardware_observation.py"),
)
FORBIDDEN_IMPORTS = {"subprocess", "requests", "httpx", "huggingface_hub", "gpu_autosetup", "llama_cpp", "local_model_commissioning"}
FORBIDDEN_CALLS = {"system", "popen", "run", "call", "check_call", "check_output"}


def main() -> int:
    findings: list[str] = []
    texts: dict[Path, str] = {}
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        texts[path] = text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            names: tuple[str, ...]
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names = (node.module or "",)
            else:
                names = ()
            for name in names:
                if name.split(".")[0] in FORBIDDEN_IMPORTS:
                    findings.append(f"{path}:forbidden_import:{name}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_CALLS:
                owner = node.func.value
                if isinstance(owner, ast.Name) and owner.id in {"os", "subprocess"}:
                    findings.append(f"{path}:forbidden_process_call:{owner.id}.{node.func.attr}")
    collectors = texts[Path("sentientos/host_collectors.py")]
    inventory = texts[Path("sentientos/host_inventory.py")]
    adapter = texts[Path("sentientos/local_model_selection.py")]
    if '"free_bytes"' not in collectors or 'disk.get("free_bytes"' not in adapter:
        findings.append("missing_free_bytes_handoff")
    if "UNKNOWN" not in adapter or "cpu_feature_source_unavailable" not in collectors:
        findings.append("missing_explicit_unknown_handling")
    if 'values["backend_family"]' in collectors or 'accelerator_values["backend_family"]' in inventory:
        findings.append("vendor_implies_backend_family")
    print("local_inference_hardware_observation_verified" if not findings else "hardware_observation_boundary_failed: " + ", ".join(sorted(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
