from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Protocol

from sentientos.attestation import (
    append_jsonl,
    as_str,
    canonical_json_bytes as attestation_canonical_json_bytes,
    compute_envelope_hash,
    iso_now,
    publish_witness,
    read_json,
    read_jsonl,
    resolve_recent_rows,
    safe_ts,
    witness_enabled,
    write_json,
)
from sentientos.artifact_catalog import append_catalog_entry

STRATEGIC_SIGN_NAMESPACE = "sentientos-strategic"
SIGNATURES_DIR = Path("glow/forge/strategic/signatures")
SIGNATURES_INDEX_PATH = SIGNATURES_DIR / "signatures_index.jsonl"


class StrategicSigner(Protocol):
    algorithm: str
    public_key_id: str

    def sign(self, payload_sha256: str) -> str: ...

    def verify(self, payload_sha256: str, signature_b64: str) -> bool: ...


class HmacTestStrategicSigner:
    algorithm = "hmac-test"

    def __init__(self, *, secret: str, public_key_id: str) -> None:
        self._secret = secret.encode("utf-8")
        self.public_key_id = public_key_id

    def sign(self, payload_sha256: str) -> str:
        digest = hmac.new(self._secret, payload_sha256.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def verify(self, payload_sha256: str, signature_b64: str) -> bool:
        return hmac.compare_digest(self.sign(payload_sha256), signature_b64)


class SshStrategicSigner:
    algorithm = "ssh-ed25519"

    def __init__(self, *, key_path: Path, allowed_signers: Path, public_key_id: str) -> None:
        self._key_path = key_path
        self._allowed_signers = allowed_signers
        self.public_key_id = public_key_id

    def sign(self, payload_sha256: str) -> str:
        with tempfile.TemporaryDirectory(prefix="sentientos-strategic-sign-") as tmp:
            msg_path = Path(tmp) / "payload.txt"
            msg_path.write_text(payload_sha256 + "\n", encoding="utf-8")
            completed = subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-n", STRATEGIC_SIGN_NAMESPACE, "-f", str(self._key_path), str(msg_path)],
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
        with tempfile.TemporaryDirectory(prefix="sentientos-strategic-verify-") as tmp:
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
                    STRATEGIC_SIGN_NAMESPACE,
                    "-s",
                    str(sig_path),
                ],
                input=(payload_sha256 + "\n").encode("utf-8"),
                capture_output=True,
                check=False,
            )
            return completed.returncode == 0


@dataclass(frozen=True)
class StrategicSig:
    schema_version: int
    kind: str
    object_id: str
    created_at: str
    path: str
    object_sha256: str
    prev_sig_hash: str | None
    sig_payload_sha256: str
    signature: str
    public_key_id: str
    algorithm: str
    sig_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "object_id": self.object_id,
            "created_at": self.created_at,
            "path": self.path,
            "object_sha256": self.object_sha256,
            "prev_sig_hash": self.prev_sig_hash,
            "sig_payload_sha256": self.sig_payload_sha256,
            "signature": self.signature,
            "public_key_id": self.public_key_id,
            "algorithm": self.algorithm,
            "sig_hash": self.sig_hash,
        }


@dataclass(frozen=True)
class StrategicVerifyResult:
    ok: bool
    reason: str | None
    checked_n: int
    last_ok_sig_hash: str | None


def canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return attestation_canonical_json_bytes(payload)


def strategic_signing_enabled() -> bool:
    return os.getenv("SENTIENTOS_STRATEGIC_SIGNING", "off") != "off"


def sign_object(
    repo_root: Path,
    *,
    kind: str,
    object_id: str,
    object_rel_path: str,
    object_payload: dict[str, object],
    created_at: str | None = None,
    goal_graph_hash: str | None = None,
) -> StrategicSig:
    signer = _resolve_signer(require_configured=True)
    root = repo_root.resolve()
    ts = created_at or iso_now()
    prev_hash = latest_sig_hash(root)
    object_sha = hashlib.sha256(canonical_json_bytes(object_payload)).hexdigest()
    signature_path = SIGNATURES_DIR / f"sig_{safe_ts(ts)}_{kind}_{_safe_id(object_id)}.json"
    payload = {
        "schema_version": 1,
        "kind": kind,
        "object_id": object_id,
        "created_at": ts,
        "path": object_rel_path,
        "object_sha256": object_sha,
        "prev_sig_hash": prev_hash,
        "public_key_id": signer.public_key_id,
        "algorithm": signer.algorithm,
    }
    payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    signature = signer.sign(payload_sha)
    envelope = dict(payload)
    envelope["sig_payload_sha256"] = payload_sha
    envelope["signature"] = signature
    envelope["sig_hash"] = compute_envelope_hash(envelope, hash_field="sig_hash")
    row = StrategicSig(
        schema_version=1,
        kind=kind,
        object_id=object_id,
        created_at=ts,
        path=object_rel_path,
        object_sha256=object_sha,
        prev_sig_hash=prev_hash,
        sig_payload_sha256=payload_sha,
        signature=signature,
        public_key_id=signer.public_key_id,
        algorithm=signer.algorithm,
        sig_hash=str(envelope["sig_hash"]),
    )
    write_json(root / signature_path, row.to_dict())
    append_jsonl(root / SIGNATURES_INDEX_PATH, row.to_dict())
    links = {"object_id": object_id, "object_kind": kind, "sig_hash": row.sig_hash}
    if goal_graph_hash:
        links["goal_graph_hash"] = goal_graph_hash
    append_catalog_entry(
        root,
        kind="strategic_signature",
        artifact_id=row.sig_hash[:24],
        relative_path=str(signature_path),
        schema_name="strategic_signature",
        schema_version=1,
        links=links,
        summary={"status": "ok", "algorithm": row.algorithm},
        ts=ts,
    )
    return row


def verify_recent(repo_root: Path, *, last: int = 20) -> StrategicVerifyResult:
    root = repo_root.resolve()
    rows = resolve_recent_rows(index_path=root / SIGNATURES_INDEX_PATH, sig_dir=root / SIGNATURES_DIR, sig_glob="sig_*.json", last_n=last)
    if not rows:
        return StrategicVerifyResult(ok=True, reason=None, checked_n=0, last_ok_sig_hash=None)
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return StrategicVerifyResult(ok=True, reason=None, checked_n=0, last_ok_sig_hash=None)
    recent = rows
    prev_hash: str | None = None
    checked_n = 0
    last_ok_sig_hash: str | None = None
    for row in recent:
        sig_hash = as_str(row.get("sig_hash"))
        payload = _signature_payload_from_record(row)
        expected_payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if as_str(row.get("sig_payload_sha256")) != expected_payload_sha:
            return StrategicVerifyResult(ok=False, reason=f"sig_payload_sha256_mismatch:{as_str(row.get('object_id')) or 'unknown'}", checked_n=checked_n, last_ok_sig_hash=last_ok_sig_hash)
        sig = as_str(row.get("signature")) or ""
        if not signer.verify(expected_payload_sha, sig):
            return StrategicVerifyResult(ok=False, reason=f"signature_invalid:{as_str(row.get('object_id')) or 'unknown'}", checked_n=checked_n, last_ok_sig_hash=last_ok_sig_hash)
        computed_sig_hash = compute_envelope_hash(row, hash_field="sig_hash")
        if sig_hash != computed_sig_hash:
            return StrategicVerifyResult(ok=False, reason=f"sig_hash_mismatch:{as_str(row.get('object_id')) or 'unknown'}", checked_n=checked_n, last_ok_sig_hash=last_ok_sig_hash)
        if prev_hash and as_str(row.get("prev_sig_hash")) != prev_hash:
            return StrategicVerifyResult(ok=False, reason=f"prev_sig_hash_mismatch:{as_str(row.get('object_id')) or 'unknown'}", checked_n=checked_n, last_ok_sig_hash=last_ok_sig_hash)
        obj_path = root / (as_str(row.get("path")) or "")
        obj_payload = read_json(obj_path)
        obj_sha = hashlib.sha256(canonical_json_bytes(obj_payload)).hexdigest()
        if as_str(row.get("object_sha256")) != obj_sha:
            return StrategicVerifyResult(ok=False, reason=f"object_sha256_mismatch:{as_str(row.get('object_id')) or 'unknown'}", checked_n=checked_n, last_ok_sig_hash=last_ok_sig_hash)
        prev_hash = sig_hash
        checked_n += 1
        last_ok_sig_hash = sig_hash
    return StrategicVerifyResult(ok=True, reason=None, checked_n=checked_n, last_ok_sig_hash=last_ok_sig_hash)


def verify_latest(repo_root: Path, *, last: int = 20) -> tuple[bool, str | None]:
    result = verify_recent(repo_root, last=last)
    return result.ok, result.reason


def maybe_publish_strategic_witness(repo_root: Path, *, allow_git_tag_publish: bool = True) -> tuple[dict[str, object], str | None]:
    if not witness_enabled("SENTIENTOS_STRATEGIC_WITNESS_PUBLISH"):
        status = {"status": "disabled", "published_at": None, "failure": None, "tag": None}
        write_json(repo_root.resolve() / "glow/federation/strategic_witness_status.json", status)
        return status, None
    root = repo_root.resolve()
    latest = latest_signature(root)
    if latest is None:
        status = {"status": "failed", "published_at": None, "failure": "strategic_signature_missing", "tag": None}
        write_json(root / "glow/federation/strategic_witness_status.json", status)
        return _enforce_witness(status)
    short = latest.sig_hash[:16]
    day = latest.created_at[:10]
    tag = f"sentientos-strategy/{day}/{short}"
    backend = os.getenv("SENTIENTOS_STRATEGIC_WITNESS_BACKEND", "git")
    witness = publish_witness(
        repo_root=root,
        backend=backend,
        tag=tag,
        message=f"strategic_sig_hash: {latest.sig_hash}\nobject_id: {latest.object_id}\nkind: {latest.kind}",
        file_path=root / "glow/federation/strategic_witness_tags.jsonl",
        file_row={"tag": tag, "sig_hash": latest.sig_hash, "published_at": iso_now()},
        allow_git_tag_publish=allow_git_tag_publish,
    )
    status = {"status": witness.status, "published_at": witness.published_at, "failure": witness.failure, "tag": tag, "sig_hash": short}
    if status["status"] == "ok":
        append_catalog_entry(
            root,
            kind="strategic_witness_publish",
            artifact_id=short,
            relative_path="glow/federation/strategic_witness_tags.jsonl" if backend == "file" else "",
            schema_name="strategic_witness_publish",
            schema_version=1,
            links={"sig_hash": latest.sig_hash, "object_id": latest.object_id},
            summary={"status": "ok", "tag": tag},
            ts=iso_now(),
        )
    write_json(root / "glow/federation/strategic_witness_status.json", status)
    return _enforce_witness(status)


def latest_signature(repo_root: Path) -> StrategicSig | None:
    rows = read_jsonl(repo_root.resolve() / SIGNATURES_INDEX_PATH)
    if not rows:
        return None
    payload = rows[-1]
    sig_hash = as_str(payload.get("sig_hash")) or ""
    return StrategicSig(
        schema_version=int(payload.get("schema_version") or 1),
        kind=as_str(payload.get("kind")) or "",
        object_id=as_str(payload.get("object_id")) or "",
        created_at=as_str(payload.get("created_at")) or "",
        path=as_str(payload.get("path")) or "",
        object_sha256=as_str(payload.get("object_sha256")) or "",
        prev_sig_hash=as_str(payload.get("prev_sig_hash")),
        sig_payload_sha256=as_str(payload.get("sig_payload_sha256")) or "",
        signature=as_str(payload.get("signature")) or "",
        public_key_id=as_str(payload.get("public_key_id")) or "",
        algorithm=as_str(payload.get("algorithm")) or "",
        sig_hash=sig_hash,
    )


def latest_sig_hash(repo_root: Path) -> str | None:
    item = latest_signature(repo_root)
    return item.sig_hash if item is not None else None


def latest_sig_hash_short(repo_root: Path) -> str | None:
    sig_hash = latest_sig_hash(repo_root)
    return sig_hash[:16] if sig_hash else None


def _signature_payload_from_record(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": int(payload.get("schema_version") or 1),
        "kind": as_str(payload.get("kind")) or "",
        "object_id": as_str(payload.get("object_id")) or "",
        "created_at": as_str(payload.get("created_at")) or "",
        "path": as_str(payload.get("path")) or "",
        "object_sha256": as_str(payload.get("object_sha256")) or "",
        "prev_sig_hash": as_str(payload.get("prev_sig_hash")),
        "public_key_id": as_str(payload.get("public_key_id")) or "",
        "algorithm": as_str(payload.get("algorithm")) or "",
    }


def _resolve_signer(*, require_configured: bool) -> StrategicSigner | None:
    backend = os.getenv("SENTIENTOS_STRATEGIC_SIGNING", "off")
    if backend == "off":
        if require_configured:
            raise RuntimeError("strategic_signing_disabled")
        return None
    if backend == "hmac-test":
        return HmacTestStrategicSigner(
            secret=os.getenv("SENTIENTOS_STRATEGIC_HMAC_SECRET", "sentientos-strategic-test"),
            public_key_id=os.getenv("SENTIENTOS_STRATEGIC_PUBLIC_KEY_ID", "hmac-test"),
        )
    if backend == "ssh":
        key = Path(os.getenv("SENTIENTOS_STRATEGIC_SSH_KEY", ""))
        allowed = Path(os.getenv("SENTIENTOS_STRATEGIC_ALLOWED_SIGNERS", ""))
        pub = os.getenv("SENTIENTOS_STRATEGIC_PUBLIC_KEY_ID", "")
        if not key or not allowed or not pub:
            raise RuntimeError("strategic_signing_config_missing")
        return SshStrategicSigner(key_path=key, allowed_signers=allowed, public_key_id=pub)
    raise RuntimeError(f"strategic_signing_backend_unknown:{backend}")


def _enforce_witness(status: dict[str, object]) -> tuple[dict[str, object], str | None]:
    failure = _as_str(status.get("failure"))
    if failure and os.getenv("SENTIENTOS_STRATEGIC_WITNESS_ENFORCE", "0") == "1":
        return status, failure
    return status, None


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)[:80]


def _as_str(value: object) -> str | None:
    return as_str(value)

