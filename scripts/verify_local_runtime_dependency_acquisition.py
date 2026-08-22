"""Static boundary verifier for dependency bundle acquisition."""
from pathlib import Path

def main() -> int:
    dependency = Path("sentientos/local_runtime_dependency_acquisition.py").read_text(encoding="utf-8")
    runtime = Path("sentientos/local_runtime_acquisition.py").read_text(encoding="utf-8")
    required = ["stream_exact", "files.pythonhosted.org", "ARTIFACT_RECEIPT_SCHEMA", "BUNDLE_RECEIPT_SCHEMA", "dependency_bundle_incomplete", "runtime_execution_authority_granted"]
    forbidden = ["subprocess.run", "subprocess.Popen", "import llama_cpp", "python -m pip", "site-packages"]
    errors = [f"missing:{token}" for token in required if token not in dependency] + [f"forbidden:{token}" for token in forbidden if token in dependency]
    if "stream_exact" not in runtime or "github.com" not in runtime: errors.append("runtime_shared_core_or_policy_missing")
    print({"status":"local_runtime_dependency_acquisition_verified" if not errors else "failed", "errors":errors}); return bool(errors)

if __name__ == "__main__": raise SystemExit(main())
