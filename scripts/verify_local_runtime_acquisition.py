"""Static boundary verifier for bounded runtime artifact acquisition."""
from __future__ import annotations
import ast
from pathlib import Path

def main() -> int:
    module=Path("sentientos/local_runtime_acquisition.py"); source=module.read_text(encoding="utf-8")
    host=Path("sentientos/host_collectors.py").read_text(encoding="utf-8"); planner=Path("sentientos/local_runtime_provisioning.py").read_text(encoding="utf-8")
    errors=[]
    if "provider(39)" not in host or "provider(40)" not in host or "provider(41)" not in host: errors.append("windows AVX IDs are not 39/40/41")
    for fact in ("validate_runtime_catalog", "provisioning_plan_digest", 'root / "sha256" / digest',
                 "artifact_size_mismatch", "artifact_hash_mismatch", "already_present_verified", "authorization_digest"):
        if fact not in source: errors.append(f"missing contract fact: {fact}")
    forbidden={"subprocess","pip","venv","llama_cpp","local_model_commissioning"}
    for node in ast.walk(ast.parse(source)):
        names=set()
        if isinstance(node,ast.Import): names={a.name.split('.')[0] for a in node.names}
        elif isinstance(node,ast.ImportFrom): names={(node.module or '').split('.')[0]}
        for name in names & forbidden: errors.append(f"forbidden import: {name}")
    if any(token in planner for token in ("urllib.request", "requests.get", "httpx")): errors.append("planner gained network authority")
    print("local_runtime_acquisition_verified" if not errors else "\n".join(errors)); return bool(errors)
if __name__ == "__main__": raise SystemExit(main())
