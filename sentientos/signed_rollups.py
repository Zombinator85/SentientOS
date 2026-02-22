from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Protocol

ROLLUP_SIGN_NAMESPACE = "sentientos-rollup"


class RollupSigner(Protocol):
    algorithm: str
    public_key_id: str

    def sign(self, payload_sha256: str) -> str: ...

    def verify(self, payload_sha256: str, signature_b64: str) -> bool: ...


class HmacTestRollupSigner:
    algorithm = "hmac-test"

    def __init__(self, *, secret: str, public_key_id: str) -> None:
        self._secret = secret.encode("utf-8")
        self.public_key_id = public_key_id

    def sign(self, payload_sha256: str) -> str:
        digest = hmac.new(self._secret, payload_sha256.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def verify(self, payload_sha256: str, signature_b64: str) -> bool:
        return hmac.compare_digest(self.sign(payload_sha256), signature_b64)


class SshRollupSigner:
    algorithm = "ssh-ed25519"

    def __init__(self, *, key_path: Path, allowed_signers: Path, public_key_id: str) -> None:
        self._key_path = key_path
        self._allowed_signers = allowed_signers
        self.public_key_id = public_key_id

    def sign(self, payload_sha256: str) -> str:
        with tempfile.TemporaryDirectory(prefix="sentientos-rollup-sign-") as tmp:
            msg_path = Path(tmp) / "payload.txt"
            msg_path.write_text(payload_sha256 + "\n", encoding="utf-8")
            completed = subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-n", ROLLUP_SIGN_NAMESPACE, "-f", str(self._key_path), str(msg_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"ssh_sign_failed:{completed.stderr.strip()}")
            return base64.b64encode(msg_path.with_suffix(".txt.sig").read_bytes()).decode("ascii")

    def verify(self, payload_sha256: str, signature_b64: str) -> bool:
        try:
            sig = base64.b64decode(signature_b64.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return False
        with tempfile.TemporaryDirectory(prefix="sentientos-rollup-verify-") as tmp:
            sig_path = Path(tmp) / "payload.sig"
            sig_path.write_bytes(sig)
            completed = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(self._allowed_signers),
                    "-I",
                    self.public_key_id,
                    "-n",
                    ROLLUP_SIGN_NAMESPACE,
                    "-s",
                    str(sig_path),
                ],
                input=(payload_sha256 + "\n").encode("utf-8"),
                capture_output=True,
                check=False,
            )
            return completed.returncode == 0


@dataclass(frozen=True)
class RollupSignature:
    schema_version: int
    rollup_id: str
    created_at: str
    stream_name: str
    rollup_path: str
    rollup_sha256: str
    prev_rollup_sig_hash: str | None
    sig_payload_sha256: str
    signature: str
    public_key_id: str
    algorithm: str
    signature_hash: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rollup_id": self.rollup_id,
            "created_at": self.created_at,
            "stream_name": self.stream_name,
            "rollup_path": self.rollup_path,
            "rollup_sha256": self.rollup_sha256,
            "prev_rollup_sig_hash": self.prev_rollup_sig_hash,
            "sig_payload_sha256": self.sig_payload_sha256,
            "signature": self.signature,
            "public_key_id": self.public_key_id,
            "algorithm": self.algorithm,
            "signature_hash": self.signature_hash,
        }


def canonical_payload_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _signature_hash_bytes(payload: dict[str, object]) -> bytes:
    item = dict(payload)
    item.pop("signature_hash", None)
    return canonical_payload_bytes(item)


def sign_rollups(repo_root: Path, rollup_files: list[str]) -> list[RollupSignature]:
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return []
    root = repo_root.resolve()
    signed: list[RollupSignature] = []
    for rel in sorted(rollup_files):
        if "/rollup_" not in rel:
            continue
        item = _sign_rollup(root, Path(rel), signer)
        if item is not None:
            signed.append(item)
    return signed


def sign_existing_unsigned_rollups(repo_root: Path) -> list[RollupSignature]:
    root = repo_root.resolve()
    items = [str(path.relative_to(root)) for path in sorted((root / "glow/forge/rollups").glob("*/rollup_*.json"), key=lambda p: p.as_posix())]
    return sign_rollups(root, items)


def verify_signed_rollups(repo_root: Path, *, last_weeks: int | None = None) -> tuple[bool, str | None]:
    root = repo_root.resolve()
    streams = sorted((root / "glow/forge/rollups").glob("*/signatures/sig_*.json"), key=lambda p: p.as_posix())
    grouped: dict[str, list[Path]] = {}
    for sig in streams:
        stream = sig.parent.parent.name
        grouped.setdefault(stream, []).append(sig)
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return True, None
    for stream, paths in grouped.items():
        ordered = sorted(paths, key=lambda p: p.name)
        if isinstance(last_weeks, int) and last_weeks > 0:
            ordered = ordered[-last_weeks:]
        prev_hash: str | None = None
        for path in ordered:
            payload = _read_json(path)
            if not payload:
                return False, f"signature_missing:{path}"
            if _as_str(payload.get("stream_name")) != stream:
                return False, f"stream_mismatch:{path}"
            expected_prev = _as_str(payload.get("prev_rollup_sig_hash"))
            if expected_prev != prev_hash:
                return False, f"prev_link_mismatch:{path}:expected={prev_hash}:found={expected_prev}"
            rollup_path = root / (_as_str(payload.get("rollup_path")) or "")
            rollup_sha = _sha256_file(rollup_path)
            if rollup_sha != _as_str(payload.get("rollup_sha256")):
                return False, f"rollup_sha_mismatch:{path}:expected={_as_str(payload.get('rollup_sha256'))}:found={rollup_sha}"
            signed_payload = _signature_payload_from_record(payload)
            payload_sha = hashlib.sha256(canonical_payload_bytes(signed_payload)).hexdigest()
            if payload_sha != _as_str(payload.get("sig_payload_sha256")):
                return False, f"sig_payload_sha_mismatch:{path}"
            if not signer.verify(payload_sha, _as_str(payload.get("signature")) or ""):
                return False, f"signature_verify_failed:{path}"
            computed_sig_hash = hashlib.sha256(_signature_hash_bytes(payload)).hexdigest()
            if _as_str(payload.get("signature_hash")) != computed_sig_hash:
                return False, f"signature_hash_mismatch:{path}"
            prev_hash = computed_sig_hash
    return True, None


def maybe_sign_catalog_checkpoint(repo_root: Path) -> dict[str, object] | None:
    if os.getenv("SENTIENTOS_SIGN_CATALOG_CHECKPOINT", "0") != "1":
        return None
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return None
    root = repo_root.resolve()
    catalog_path = root / "pulse/artifact_catalog.jsonl"
    catalog_sha = _sha256_file(catalog_path)
    created_at = _iso_now()
    payload = {
        "schema_version": 1,
        "checkpoint_id": created_at,
        "created_at": created_at,
        "catalog_path": "pulse/artifact_catalog.jsonl",
        "catalog_sha256": catalog_sha,
        "public_key_id": signer.public_key_id,
        "algorithm": signer.algorithm,
    }
    payload_sha = hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()
    signature = signer.sign(payload_sha)
    envelope = dict(payload)
    envelope["sig_payload_sha256"] = payload_sha
    envelope["signature"] = signature
    envelope["signature_hash"] = hashlib.sha256(_signature_hash_bytes(envelope)).hexdigest()
    dir_path = root / "glow/forge/catalog_checkpoints"
    dir_path.mkdir(parents=True, exist_ok=True)
    target = dir_path / f"checkpoint_{_safe_ts(created_at)}.json"
    _write_json(target, envelope)
    _append_jsonl(dir_path / "checkpoints_index.jsonl", envelope)
    return envelope


def latest_rollup_signature_hashes(repo_root: Path) -> dict[str, str]:
    root = repo_root.resolve()
    out: dict[str, str] = {}
    for stream_dir in sorted((root / "glow/forge/rollups").glob("*/signatures"), key=lambda p: p.as_posix()):
        latest = sorted(stream_dir.glob("sig_*.json"), key=lambda p: p.name)
        if latest:
            payload = _read_json(latest[-1])
            sig_hash = _as_str(payload.get("signature_hash"))
            if sig_hash:
                out[stream_dir.parent.name] = sig_hash[:16]
    return out


def latest_catalog_checkpoint_hash(repo_root: Path) -> str | None:
    rows = _read_jsonl(repo_root.resolve() / "glow/forge/catalog_checkpoints/checkpoints_index.jsonl")
    if not rows:
        return None
    sig_hash = _as_str(rows[-1].get("signature_hash"))
    return sig_hash[:16] if sig_hash else None


def maybe_publish_rollup_witness(repo_root: Path) -> tuple[dict[str, object], str | None]:
    if os.getenv("SENTIENTOS_ROLLUP_WITNESS_PUBLISH", "0") != "1":
        return {"status": "disabled", "last_rollup_id": None, "published_at": None, "failure": None}, None
    root = repo_root.resolve()
    latest_sig = sorted((root / "glow/forge/rollups").glob("*/signatures/sig_*.json"), key=lambda p: p.as_posix())
    if not latest_sig:
        return {"status": "failed", "last_rollup_id": None, "published_at": None, "failure": "signature_missing"}, "signature_missing"
    payload = _read_json(latest_sig[-1])
    rollup_id = _as_str(payload.get("rollup_id"))
    if not rollup_id:
        return {"status": "failed", "last_rollup_id": None, "published_at": None, "failure": "rollup_id_missing"}, "rollup_id_missing"
    tag = f"sentientos-rollup/{rollup_id}"
    if _git_tag_exists(root, tag):
        return {"status": "ok", "last_rollup_id": rollup_id, "published_at": None, "failure": None}, None
    message = f"rollup_id: {rollup_id}\nsignature_hash: {_as_str(payload.get('signature_hash')) or ''}"
    completed = subprocess.run(["git", "tag", "-a", tag, "-m", message], cwd=root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "tag_create_failed"
        status = {"status": "failed", "last_rollup_id": rollup_id, "published_at": None, "failure": detail[:240]}
        if os.getenv("SENTIENTOS_ROLLUP_WITNESS_ENFORCE", "0") == "1":
            return status, detail
        return status, None
    return {"status": "ok", "last_rollup_id": rollup_id, "published_at": _iso_now(), "failure": None}, None


def _sign_rollup(root: Path, rel_path: Path, signer: RollupSigner) -> RollupSignature | None:
    rollup_path = root / rel_path
    if not rollup_path.exists():
        return None
    stream = rollup_path.parent.name
    week = rollup_path.stem.replace("rollup_", "")
    sig_path = root / "glow/forge/rollups" / stream / "signatures" / f"sig_{week}.json"
    if sig_path.exists():
        return None
    created_at = _iso_now()
    rollup_id = f"{stream}:{week}"
    prev_hash = _latest_signature_hash(root, stream)
    payload = {
        "schema_version": 1,
        "rollup_id": rollup_id,
        "created_at": created_at,
        "stream_name": stream,
        "rollup_path": str(rel_path),
        "rollup_sha256": _sha256_file(rollup_path),
        "prev_rollup_sig_hash": prev_hash,
        "public_key_id": signer.public_key_id,
        "algorithm": signer.algorithm,
    }
    payload_sha = hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()
    signature = signer.sign(payload_sha)
    envelope = RollupSignature(
        schema_version=1,
        rollup_id=rollup_id,
        created_at=created_at,
        stream_name=stream,
        rollup_path=str(rel_path),
        rollup_sha256=_sha256_file(rollup_path),
        prev_rollup_sig_hash=prev_hash,
        sig_payload_sha256=payload_sha,
        signature=signature,
        public_key_id=signer.public_key_id,
        algorithm=signer.algorithm,
        signature_hash=None,
    )
    obj = envelope.to_dict()
    obj["signature_hash"] = hashlib.sha256(_signature_hash_bytes(obj)).hexdigest()
    final = RollupSignature(**obj)
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(sig_path, final.to_dict())
    _append_jsonl(sig_path.parent / "signatures_index.jsonl", final.to_dict())
    return final


def _signature_payload_from_record(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": int(payload.get("schema_version") or 1),
        "rollup_id": _as_str(payload.get("rollup_id")) or "",
        "created_at": _as_str(payload.get("created_at")) or "",
        "stream_name": _as_str(payload.get("stream_name")) or "",
        "rollup_path": _as_str(payload.get("rollup_path")) or "",
        "rollup_sha256": _as_str(payload.get("rollup_sha256")) or "",
        "prev_rollup_sig_hash": _as_str(payload.get("prev_rollup_sig_hash")),
        "public_key_id": _as_str(payload.get("public_key_id")) or "",
        "algorithm": _as_str(payload.get("algorithm")) or "",
    }


def _latest_signature_hash(root: Path, stream: str) -> str | None:
    sigs = sorted((root / "glow/forge/rollups" / stream / "signatures").glob("sig_*.json"), key=lambda p: p.name)
    if not sigs:
        return None
    payload = _read_json(sigs[-1])
    return _as_str(payload.get("signature_hash"))


def _resolve_signer(*, require_configured: bool) -> RollupSigner | None:
    backend = os.getenv("SENTIENTOS_ROLLUP_SIGNING", "off")
    if backend == "off":
        if require_configured:
            raise RuntimeError("rollup_signing_disabled")
        return None
    if backend == "hmac-test":
        return HmacTestRollupSigner(
            secret=os.getenv("SENTIENTOS_ROLLUP_HMAC_SECRET", "sentientos-rollup-test"),
            public_key_id=os.getenv("SENTIENTOS_ROLLUP_PUBLIC_KEY_ID", "hmac-test"),
        )
    if backend == "ssh":
        key = Path(os.getenv("SENTIENTOS_ROLLUP_SSH_KEY", ""))
        allowed = Path(os.getenv("SENTIENTOS_ROLLUP_ALLOWED_SIGNERS", ""))
        pub = os.getenv("SENTIENTOS_ROLLUP_PUBLIC_KEY_ID", "")
        if not key or not allowed or not pub:
            raise RuntimeError("rollup_signing_config_missing")
        return SshRollupSigner(key_path=key, allowed_signers=allowed, public_key_id=pub)
    raise RuntimeError(f"rollup_signing_backend_unknown:{backend}")


def _sha256_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()


def _safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, object]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _git_tag_exists(repo_root: Path, tag: str) -> bool:
    completed = subprocess.run(["git", "rev-parse", "--verify", f"refs/tags/{tag}"], cwd=repo_root, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
