from __future__ import annotations

import argparse

try:
    from scripts.cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root
except ModuleNotFoundError:  # script execution fallback
    from cli_common import emit_payload, ensure_repo_on_path, exit_code, resolve_repo_root

ensure_repo_on_path(__file__)

from sentientos.attestation import read_json
from sentientos.system_constitution import (
    SYSTEM_CONSTITUTION_REL,
    compose_system_constitution,
    verify_constitution,
    write_constitution_artifacts,
)


def _latest(root):
    path = root / SYSTEM_CONSTITUTION_REL
    payload = read_json(path)
    if payload:
        return payload
    return compose_system_constitution(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic System Constitution surface")
    parser.add_argument("--repo-root", help="repository root (defaults to current working directory)")
    parser.add_argument("--json", action="store_true", help="compose/write constitution and print canonical JSON")
    parser.add_argument("--latest", action="store_true", help="print latest constitution summary")
    parser.add_argument("--verify", action="store_true", help="verify constitution composition and return constitutional exit code")
    args = parser.parse_args(argv)

    selected = int(args.json) + int(args.latest) + int(args.verify)
    if selected != 1:
        parser.error("choose exactly one of --json, --latest, or --verify")
        return 3

    root = resolve_repo_root(args.repo_root)
    if args.json:
        payload = compose_system_constitution(root)
        refs = payload.get("constitutional_refs") if isinstance(payload.get("constitutional_refs"), dict) else {}
        payload["resolution_paths"] = refs.get("artifact_paths", {}) if isinstance(refs, dict) else {}
        write_constitution_artifacts(root, payload=payload)
        emit_payload(payload, as_json=True, text_renderer=lambda _: "")
        return exit_code(payload)

    if args.latest:
        payload = _latest(root)
        state = payload.get("constitution_state", "unknown")
        digest = payload.get("constitutional_digest")
        posture = ((payload.get("runtime_posture") or {}) if isinstance(payload.get("runtime_posture"), dict) else {}).get("effective_posture")
        governor_mode = ((payload.get("runtime_posture") or {}) if isinstance(payload.get("runtime_posture"), dict) else {}).get("governor_mode")
        print(f"constitution_state={state} digest={digest} posture={posture} governor_mode={governor_mode}")
        return exit_code(payload)

    payload, code = verify_constitution(root)
    write_constitution_artifacts(root, payload=payload)
    print(
        "verify="
        f"{payload.get('constitution_state')} exit_code={code} digest={payload.get('constitutional_digest')} "
        f"resolution_paths={len(((payload.get('constitutional_refs') or {}) if isinstance(payload.get('constitutional_refs'), dict) else {}).get('artifact_paths', {}))}"
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
