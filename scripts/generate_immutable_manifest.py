from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from sentientos.control_plane_kernel import AuthorityClass, LifecyclePhase, get_control_plane_kernel
from sentientos.constitutional_mutation_fabric import (
    TypedMutationAction,
    MutationProvenanceIntent,
    get_constitutional_mutation_router,
)
from sentientos.protected_mutation_provenance import validate_admission_provenance

DEFAULT_MANIFEST = Path("vow/immutable_manifest.json")
DEFAULT_FILES = (
    Path("NEWLEGACY.txt"),
    Path("vow/config.yaml"),
    Path("vow/invariants.yaml"),
    Path("vow/init.py"),
    Path("scripts/audit_immutability_verifier.py"),
    Path("scripts/verify_audits.py"),
)
SCHEMA_VERSION = 1
TOOL_VERSION = "1"
CANONICAL_TYPED_ACTION_ID = "sentientos.manifest.generate"
CANONICAL_ROUTER_ID = "constitutional_mutation_router.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def generate_manifest(
    *,
    output: Path,
    files: tuple[Path, ...] = DEFAULT_FILES,
    allow_missing_files: bool = False,
    admission_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(admission_context, dict):
        raise ValueError("non_canonical_mutation_path:sentientos.manifest.generate")
    validate_admission_provenance(admission_context, expect_execution=True)
    if (
        str(admission_context.get("typed_action_id") or "") != CANONICAL_TYPED_ACTION_ID
        or str(admission_context.get("canonical_router") or "") != CANONICAL_ROUTER_ID
        or str(admission_context.get("path_status") or "") != "canonical_router"
    ):
        raise ValueError("non_canonical_mutation_path:sentientos.manifest.generate")

    manifest_files: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for path in sorted(files, key=lambda item: item.as_posix()):
        normalized = path.as_posix()
        if not path.exists():
            missing.append(normalized)
            continue
        manifest_files[normalized] = {
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        }

    if missing and not allow_missing_files:
        raise FileNotFoundError(f"immutable manifest inputs missing: {', '.join(missing)}")

    manifest_hash = hashlib.sha256(_canonical_json(manifest_files).encode("utf-8")).hexdigest()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "sentientos_immutable",
        "generated_by": "scripts.generate_immutable_manifest",
        "tool_version": TOOL_VERSION,
        "captured_by": _git_sha(),
        "manifest_sha256": manifest_hash,
        "canonical_serialization": {
            "sort_keys": True,
            "separators": [",", ":"],
            "path_normalization": "posix_relative",
        },
        "files": manifest_files,
    }
    if missing:
        payload["degraded_mode"] = {
            "active": True,
            "reason": "manifest_inputs_missing",
            "missing_files": missing,
        }
    payload["admission"] = dict(admission_context)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def execute_manifest_generation_action(
    *,
    output: Path,
    allow_missing_files: bool,
    execution_source: str,
    execution_owner: str,
) -> dict[str, Any]:
    from sentientos import constitutional_mutation_fabric as _fabric

    _fabric.get_control_plane_kernel = get_control_plane_kernel
    router = get_constitutional_mutation_router()
    router.register_handler(
        CANONICAL_TYPED_ACTION_ID,
        lambda _action, _admission: generate_manifest(
            output=output,
            allow_missing_files=allow_missing_files,
            admission_context=_admission,
        ),
    )
    action = TypedMutationAction(
        action_id=CANONICAL_TYPED_ACTION_ID,
        mutation_domain="immutable_manifest_identity_writes",
        authority_class=AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,
        lifecycle_phase=LifecyclePhase.MAINTENANCE,
        correlation_id=f"manifest:{output.as_posix()}",
        execution_owner=execution_owner,
        execution_source=execution_source,
        target_subsystem=str(output),
        action_kind="generate_immutable_manifest",
        provenance_intent=MutationProvenanceIntent(
            domains=("immutable_manifest_identity_writes",),
            authority_classes=(AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION.value,),
            invocation_path=execution_source,
            expect_forward_enforcement=True,
        ),
        payload={
            "requested_by": "scripts/generate_immutable_manifest.py",
        },
    )
    result = router.execute(action)
    if not result.executed or not isinstance(result.handler_result, dict):
        raise RuntimeError(f"kernel_denied:{','.join(result.decision_reason_codes)}")
    return result.handler_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic immutable manifest")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="manifest output path")
    parser.add_argument(
        "--allow-missing-files",
        action="store_true",
        help="allow degraded mode when one or more manifest input files are missing",
    )
    args = parser.parse_args(argv)
    try:
        payload = execute_manifest_generation_action(
            output=Path(args.manifest),
            allow_missing_files=args.allow_missing_files,
            execution_source="scripts.generate_immutable_manifest.main",
            execution_owner="operator_cli",
        )
        correlation_id = str(payload.get("admission", {}).get("correlation_id", f"manifest:{Path(args.manifest).as_posix()}"))
    except RuntimeError as exc:
        reason = str(exc).removeprefix("kernel_denied:")
        print(
            json.dumps(
                {
                    "tool": "generate_immutable_manifest",
                    "status": "blocked",
                    "reason_codes": [reason] if reason else ["kernel_denied"],
                    "correlation_id": f"manifest:{Path(args.manifest).as_posix()}",
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
                {
                    "tool": "generate_immutable_manifest",
                    "output": args.manifest,
                    "degraded": bool(payload.get("degraded_mode", {}).get("active", False)),
                    "correlation_id": correlation_id,
                },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
