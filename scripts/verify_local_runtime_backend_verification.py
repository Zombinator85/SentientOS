"""Structural static boundary verifier for selected-backend verification."""
import ast
from pathlib import Path

def main() -> int:
    source=Path("sentientos/local_runtime_backend_verification.py").read_text(encoding="utf-8")
    required=("verify_runtime_import(", "verify_existing(", '"-I", "-B", "-c"',
        "TemporaryDirectory", "GGML_CUDA_DEVICES", "GGML_METAL_DEVICES",
        "llama_supports_gpu_offload()", "llama_supports_rpc()", "llama_print_system_info()",
        "runtime_backend_rpc_ambiguity", "EXPECTED_REGISTRY", "runtime_backend_native_manifest_digest",
        "catalog_external_prerequisite_codes", "runtime_provisioning_plan_digest",
        "runtime_backend_accelerator_ambiguous", "os.link", "os.fsync", "already_verified_current")
    if any(token not in source for token in required): return 2
    helper=source.split("_HELPER =",1)[1].split("'''",2)[1]
    forbidden=("Llama(", "llama_backend_init(", "llama_model_load", "n_gpu_layers", "socket.", "requests.")
    if any(token in helper for token in forbidden): return 2
    tree=ast.parse(source)
    functions={node.name:node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    verify=functions.get("verify_runtime_backend")
    publish=functions.get("_publish")
    registries=functions.get("_registries")
    validate=functions.get("validate_plan")
    if not all((verify,publish,registries,validate)): return 2
    assert verify is not None and registries is not None
    calls=[(node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id,node.lineno)
           for node in ast.walk(verify) if isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute))]
    names=[name for name,_ in calls]
    if names.count("verify_runtime_import") != 1 or names.count("_publish") != 1: return 2
    if next(line for name,line in calls if name == "verify_runtime_import") > next(line for name,line in calls if name == "runner"): return 2
    if any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id == "re" for node in ast.walk(registries)): return 2
    print("local_runtime_backend_verification_verified"); return 0
if __name__ == "__main__": raise SystemExit(main())
