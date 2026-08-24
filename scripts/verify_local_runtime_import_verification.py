"""Static boundary verifier for local runtime import verification."""
from __future__ import annotations
import ast
from pathlib import Path

TARGET = Path("sentientos/local_runtime_import_verification.py")

def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    required = ("verify_existing", "verify_installation_sources", '"-I"', '"-B"',
        "LLAMA_CPP_LIB_PATH", "EXPECTED_VERSION", "package_module_path", "low_level_module_path",
        "native_library_path", "timeout=timeout_seconds", "SENTIENTOS_RUNTIME_IMPORT_RESULT=",
        "verification_receipt_root", "_publish_receipt", "RECORD", "runtime_import_source_manifest_digest",
        "package_module_identity", "low_level_module_identity", "native_library_identity",
        '"python_version", "implementation", "soabi"', "before_environment",
        "runtime_import_receipt_path_unsafe", 'canonical["status"] = "installed_verified"',
        "expected_plan = compose_verification_plan", "dict(plan) != expected_plan",
        "canonical_supplied != canonical_current", "post_expected_plan != expected_plan",
        '"installation_plan_digest"', '"installation_receipt_semantic_digest"',
        "runtime_import_source_manifest", '"entry_type": "symlink"', "os.readlink(path)",
        '"entry_type": "regular_file"')
    missing = [item for item in required if item not in text]
    tree = ast.parse(text)
    forbidden = {"Llama", "llama_backend_init", "llama_supports_gpu_offload",
                 "llama_print_system_info"}
    calls = [node.func.id for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden]
    if missing or calls:
        print({"status": "blocked", "missing": missing, "forbidden_calls": calls}); return 1
    print("local_runtime_import_verification_verified"); return 0

if __name__ == "__main__": raise SystemExit(main())
