from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROVENANCE_PATH = Path("glow/contracts/vow_artifacts_provenance.json")


def _generate_manifest_module() -> Any:
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "generate_immutable_manifest.py"
    spec = importlib.util.spec_from_file_location("generate_immutable_manifest", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load generate_immutable_manifest from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        completed = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _resolve_manifest_path() -> Path:
    if Path("/vow").exists():
        return Path("/vow/immutable_manifest.json")
    return Path("vow/immutable_manifest.json")


def _manifest_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_vow_artifacts(*, manifest_path: Path | None = None) -> dict[str, Any]:
    manifest_module = _generate_manifest_module()
    target = manifest_path or _resolve_manifest_path()
    existed = target.exists()
    if not existed:
        manifest_module.generate_manifest(output=target)

    inputs = [item.as_posix() for item in sorted(manifest_module.DEFAULT_FILES, key=lambda p: p.as_posix())]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "git_sha": _git_sha(),
        "manifest_path": str(target),
        "manifest_present": target.exists(),
        "manifest_generated": not existed,
        "manifest_sha256": _manifest_sha256(target),
        "manifest_inputs": inputs,
    }
    PROVENANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def run_immutability_verifier_main(argv: list[str] | None = None) -> int:
    return run_immutability_verifier_command(argv)


def run_immutability_verifier_command(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "audit_immutability_verifier.py"
    command = [sys.executable, str(script), *(argv or [])]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure deterministic vow artifacts are present")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    subparsers.add_parser("ensure", help="ensure immutable_manifest exists")
    verify_parser = subparsers.add_parser("verify", help="run immutability verifier with ensure preflight")
    verify_parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments forwarded to audit_immutability_verifier")

    args = parser.parse_args(argv)
    if args.command == "ensure":
        payload = ensure_vow_artifacts()
        print(json.dumps({"tool": "vow_artifacts", "command": "ensure", "manifest_generated": payload["manifest_generated"], "manifest_path": payload["manifest_path"]}, sort_keys=True))
        return 0
    if args.command == "verify":
        forwarded = args.args
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]
        return run_immutability_verifier_command(forwarded)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
