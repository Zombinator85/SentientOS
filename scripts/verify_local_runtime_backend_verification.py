"""Static boundary verifier for selected-backend verification."""
from pathlib import Path

def main() -> int:
    source=Path("sentientos/local_runtime_backend_verification.py").read_text(encoding="utf-8")
    required=("verify_runtime_import(", "verify_existing(", '"-I", "-B", "-c"',
        "TemporaryDirectory", "GGML_CUDA_DEVICES", "GGML_METAL_DEVICES",
        "llama_supports_gpu_offload()", "llama_supports_rpc()", "llama_print_system_info()",
        "runtime_backend_rpc_ambiguity", "EXPECTED_REGISTRY", "runtime_backend_native_manifest_digest")
    if any(token not in source for token in required): return 2
    helper=source.split("_HELPER =",1)[1].split("'''",2)[1]
    forbidden=("Llama(", "llama_backend_init(", "llama_model_load", "n_gpu_layers", "socket.", "requests.")
    if any(token in helper for token in forbidden): return 2
    print("local_runtime_backend_verification_verified"); return 0
if __name__ == "__main__": raise SystemExit(main())
