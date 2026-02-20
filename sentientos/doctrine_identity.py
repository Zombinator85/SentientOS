from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path


@dataclass(slots=True)
class DoctrineIdentity:
    head_sha: str
    bundle_sha256: str
    artifact_name: str | None = None
    run_id: int | None = None
    selected_via: str | None = None
    mirror_used: bool = False
    metadata_ok: bool = False
    manifest_ok: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "head_sha": self.head_sha,
            "bundle_sha256": self.bundle_sha256,
            "artifact_name": self.artifact_name,
            "run_id": self.run_id,
            "selected_via": self.selected_via,
            "mirror_used": self.mirror_used,
            "metadata_ok": self.metadata_ok,
            "manifest_ok": self.manifest_ok,
        }


def local_doctrine_identity(repo_root: Path, *, fallback_head_sha: str = "") -> DoctrineIdentity:
    manifest = _load_json(repo_root / "glow/contracts/contract_manifest.json")
    doctrine = _load_json(repo_root / "glow/contracts/stability_doctrine.json")
    head_sha = _as_str(doctrine.get("git_sha")) or fallback_head_sha
    bundle_sha256 = _as_str(manifest.get("bundle_sha256")) or _compute_bundle_sha(manifest)
    return DoctrineIdentity(
        head_sha=head_sha,
        bundle_sha256=bundle_sha256,
        metadata_ok=bool(bundle_sha256),
        manifest_ok=bool(bundle_sha256),
    )


def expected_bundle_sha256_from_receipts(repo_root: Path) -> str | None:
    receipts = sorted((repo_root / "glow/forge/receipts").glob("merge_receipt_*.json"), key=lambda item: item.name)
    for path in reversed(receipts):
        payload = _load_json(path)
        doctrine = payload.get("doctrine_identity") if isinstance(payload.get("doctrine_identity"), dict) else {}
        value = _as_str(doctrine.get("bundle_sha256"))
        if value:
            return value
    return None


def verify_doctrine_identity(repo_root: Path) -> tuple[bool, dict[str, object]]:
    local = local_doctrine_identity(repo_root)
    expected = expected_bundle_sha256_from_receipts(repo_root)
    enforce = os.getenv("SENTIENTOS_DOCTRINE_IDENTITY_ENFORCE", "0") == "1"
    warn = os.getenv("SENTIENTOS_DOCTRINE_IDENTITY_WARN", "0") == "1"
    mismatch = bool(expected and local.bundle_sha256 and expected != local.bundle_sha256)
    ok = not mismatch or not enforce
    payload: dict[str, object] = {
        "schema_version": 1,
        "ok": ok,
        "warn_only": mismatch and warn and not enforce,
        "mismatch": mismatch,
        "local": local.to_dict(),
        "expected_bundle_sha256": expected,
    }
    return ok, payload


def _compute_bundle_sha(manifest: dict[str, object]) -> str:
    hashes = manifest.get("file_sha256") if isinstance(manifest.get("file_sha256"), dict) else {}
    canonical = "".join(
        f"{key}\n{value}\n" for key, value in sorted((k, v) for k, v in hashes.items() if isinstance(k, str) and isinstance(v, str))
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() if canonical else ""


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
