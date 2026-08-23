"""Static verifier for the bounded offline installation authority."""
from pathlib import Path

def main() -> int:
    source = Path("sentientos/local_runtime_installation.py").read_text(encoding="utf-8")
    required = ["verify_runtime_custody", "verify_dependency_bundle_custody", "system_site_packages=False",
        '"--no-index"', '"--no-deps"', '"--no-cache-dir"', '"--no-compile"', "verify_records",
        "staging.rename(final)", '"runtime_available_for_import": False', '"dependency_resolution_performed": False',
        '"verified_source_path"', "verify_installation_sources(plan, wheel_paths)", "_stream_identity(inp, out)",
        'staging / "input-wheels"', "build_offline_pip_argv(vpy, staged_paths)",
        "expected = _expected_receipt(plan, expected_auth, installed, records)", "if receipt != expected"]
    forbidden = ["import llama_cpp", "--upgrade-deps", '"--upgrade"', "shell=True", "http://", "https://",
        "import requests", "import httpx", "import urllib", "editable"]
    errors = [f"missing:{x}" for x in required if x not in source]
    errors += [f"forbidden:{x}" for x in forbidden if x in source]
    status = "local_runtime_installation_verified" if not errors else "failed"
    print({"status":status, "errors":errors}); return bool(errors)

if __name__ == "__main__": raise SystemExit(main())
