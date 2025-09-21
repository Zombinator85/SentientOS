"""Utilities for maintaining the immutable manifest."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

DEFAULT_MANIFEST_PATH = Path("/vow/immutable_manifest.json")

_DEFAULT_SIGNING_KEY = Path("/vow/keys/ed25519_private.key")
_DEFAULT_VERIFY_KEY = Path("/vow/keys/ed25519_public.key")

_SIGNING_KEY_ENV = "IMMUTABILITY_SIGNING_KEY"
_VERIFY_KEY_ENV = "IMMUTABILITY_VERIFY_KEY"
_MANIFEST_PATH_ENV = "IMMUTABILITY_MANIFEST_PATH"

_PROTECTED_NAMES = {
    "init.py",
    "privilege.py",
    "NEWLEGACY.txt",
    "vow/init.py",
}

_SIGNING_KEY_CACHE: SigningKey | None = None
_VERIFY_KEY_CACHE: VerifyKey | None = None


def reset_key_cache() -> None:
    """Clear cached signing and verify keys (useful for tests)."""

    global _SIGNING_KEY_CACHE, _VERIFY_KEY_CACHE
    _SIGNING_KEY_CACHE = None
    _VERIFY_KEY_CACHE = None


def _resolve_manifest_path(manifest_path: Path | None = None) -> Path:
    if manifest_path is not None:
        return manifest_path
    env_path = os.getenv(_MANIFEST_PATH_ENV)
    if env_path:
        return Path(env_path)
    return DEFAULT_MANIFEST_PATH


def _resolve_signing_key_path() -> Path:
    env_path = os.getenv(_SIGNING_KEY_ENV) or os.getenv("PULSE_SIGNING_KEY")
    return Path(env_path) if env_path else _DEFAULT_SIGNING_KEY


def _resolve_verify_key_path() -> Path:
    env_path = os.getenv(_VERIFY_KEY_ENV) or os.getenv("PULSE_VERIFY_KEY")
    return Path(env_path) if env_path else _DEFAULT_VERIFY_KEY


def _load_signing_key() -> SigningKey:
    global _SIGNING_KEY_CACHE
    if _SIGNING_KEY_CACHE is not None:
        return _SIGNING_KEY_CACHE
    path = _resolve_signing_key_path()
    try:
        key = SigningKey(path.read_bytes())
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Manifest signing key missing at {path}. Provision the integrity key."
        ) from exc
    _SIGNING_KEY_CACHE = key
    return key


def _load_verify_key() -> VerifyKey | None:
    global _VERIFY_KEY_CACHE
    if _VERIFY_KEY_CACHE is not None:
        return _VERIFY_KEY_CACHE
    path = _resolve_verify_key_path()
    if path.exists():
        _VERIFY_KEY_CACHE = VerifyKey(path.read_bytes())
        return _VERIFY_KEY_CACHE
    try:
        signing = _load_signing_key()
    except RuntimeError:
        return None
    _VERIFY_KEY_CACHE = signing.verify_key
    return _VERIFY_KEY_CACHE


def _canonical_path(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if text.startswith("/"):
        text = text[1:]
    return text


def is_protected_path(path: str | Path) -> bool:
    """Return ``True`` if ``path`` should never be updated by automation."""

    candidate = _canonical_path(path)
    if candidate in _PROTECTED_NAMES:
        return True
    if candidate.startswith("vow/"):
        return candidate in _PROTECTED_NAMES
    return False


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_files(files: Mapping[str, Mapping[str, object]]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _signature_payload(
    files: Mapping[str, Mapping[str, object]],
    generated: str,
    manifest_sha256: str,
) -> bytes:
    data = {
        "files": files,
        "generated": generated,
        "manifest_sha256": manifest_sha256,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign_manifest(
    files: Mapping[str, Mapping[str, object]],
    generated: str,
    manifest_sha256: str,
) -> str:
    signing_key = _load_signing_key()
    payload = _signature_payload(files, generated, manifest_sha256)
    signature = signing_key.sign(payload).signature
    return base64.b64encode(signature).decode("ascii")


def verify_manifest_signature(manifest: Mapping[str, object]) -> bool:
    signature = manifest.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    files = manifest.get("files")
    generated = manifest.get("generated")
    manifest_sha = manifest.get("manifest_sha256")
    if not isinstance(files, Mapping) or not isinstance(generated, str):
        return False
    if not isinstance(manifest_sha, str):
        return False
    verify_key = _load_verify_key()
    if verify_key is None:
        return False
    payload = _signature_payload(files, generated, manifest_sha)
    try:
        verify_key.verify(payload, base64.b64decode(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


def read_manifest(manifest_path: Path | None = None) -> dict[str, object]:
    path = _resolve_manifest_path(manifest_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", {})
    if not isinstance(files, Mapping):
        raise ValueError("manifest missing files map")
    files_copy: dict[str, Mapping[str, object]] = copy.deepcopy(dict(files))
    expected_hash = _hash_files(files_copy)
    stored_hash = data.get("manifest_sha256")
    if isinstance(stored_hash, str) and stored_hash != expected_hash:
        raise ValueError("manifest hash mismatch")
    signature = data.get("signature")
    if signature:
        if not verify_manifest_signature(
            {"files": files_copy, "generated": data.get("generated", ""), "manifest_sha256": expected_hash, "signature": signature}
        ):
            raise ValueError("manifest signature mismatch")
    else:
        data["manifest_sha256"] = expected_hash
    data["files"] = {str(key): value for key, value in files_copy.items()}
    return data


def update_manifest(
    files_changed: Iterable[str | Path],
    *,
    manifest_path: Path | None = None,
    timestamp: datetime | None = None,
) -> dict[str, object]:
    path = _resolve_manifest_path(manifest_path)
    try:
        manifest = read_manifest(path)
    except FileNotFoundError:
        manifest = {"files": {}, "generated": datetime.now(timezone.utc).isoformat()}
    files_section = manifest.get("files")
    if not isinstance(files_section, dict):
        files_section = {}
    files_section = {str(k): dict(v) for k, v in files_section.items()}

    normalized: list[str] = []
    seen: set[str] = set()
    for entry in files_changed:
        raw_path = str(Path(str(entry)))
        candidate = _canonical_path(raw_path)
        if not candidate or is_protected_path(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(raw_path)

    if not normalized:
        manifest["files"] = files_section
        manifest["manifest_sha256"] = _hash_files(files_section)
        generated = manifest.get("generated")
        if isinstance(generated, str):
            manifest["signature"] = _sign_manifest(
                files_section, generated, manifest["manifest_sha256"]
            )
        return manifest

    now = timestamp or datetime.now(timezone.utc)
    generated = now.astimezone(timezone.utc).isoformat()

    for rel_path in normalized:
        file_path = Path(rel_path)
        if not file_path.is_file():
            continue
        files_section[rel_path] = {
            "sha256": _hash_file(file_path),
            "timestamp": generated,
        }

    manifest["files"] = files_section
    manifest["generated"] = generated
    manifest_hash = _hash_files(files_section)
    manifest["manifest_sha256"] = manifest_hash
    manifest["signature"] = _sign_manifest(files_section, generated, manifest_hash)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
