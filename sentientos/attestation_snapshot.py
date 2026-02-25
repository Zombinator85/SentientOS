from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import subprocess
import tempfile

from sentientos.attestation import (
    VerifyResult,
    append_jsonl,
    as_str,
    canonical_json_bytes,
    compute_envelope_hash,
    parse_verify_policy,
    publish_witness,
    read_json,
    read_jsonl,
    resolve_recent_rows,
    safe_ts,
    write_json,
)

SNAPSHOT_DIR = Path("glow/forge/attestation/snapshots")
SNAPSHOT_PULSE_PATH = Path("pulse/attestation_snapshots.jsonl")
SIGNATURE_DIR = Path("glow/forge/attestation/signatures/attestation_snapshots")
SIGNATURE_INDEX_PATH = SIGNATURE_DIR / "signatures_index.jsonl"


@dataclass(frozen=True)
class AttestationSnapshot:
    schema_version: int
    ts: str
    policy_hash: str
    integrity_status_hash: str
    latest_rollup_sig_hash: str | None
    latest_strategic_sig_hash: str | None
    latest_goal_graph_hash: str | None
    latest_catalog_checkpoint_hash: str | None
    doctrine_bundle_sha256: str | None
    witness_summary: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ts": self.ts,
            "policy_hash": self.policy_hash,
            "integrity_status_hash": self.integrity_status_hash,
            "latest_rollup_sig_hash": self.latest_rollup_sig_hash,
            "latest_strategic_sig_hash": self.latest_strategic_sig_hash,
            "latest_goal_graph_hash": self.latest_goal_graph_hash,
            "latest_catalog_checkpoint_hash": self.latest_catalog_checkpoint_hash,
            "doctrine_bundle_sha256": self.doctrine_bundle_sha256,
            "witness_summary": self.witness_summary,
        }


def emit_snapshot(repo_root: Path, snapshot: AttestationSnapshot) -> str:
    root = repo_root.resolve()
    rel = SNAPSHOT_DIR / f"snapshot_{safe_ts(snapshot.ts)}.json"
    write_json(root / rel, snapshot.to_dict())
    append_jsonl(root / SNAPSHOT_PULSE_PATH, snapshot.to_dict() | {"path": str(rel)})
    return str(rel)


def maybe_sign_snapshot(repo_root: Path, *, snapshot_rel_path: str, snapshot_payload: dict[str, object]) -> dict[str, object] | None:
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return None
    root = repo_root.resolve()
    prev = _latest_sig_hash(root)
    payload = {
        "schema_version": 1,
        "kind": "attestation_snapshot",
        "object_id": as_str(snapshot_payload.get("ts")) or "unknown",
        "created_at": as_str(snapshot_payload.get("ts")) or "",
        "path": snapshot_rel_path,
        "object_sha256": hashlib.sha256(canonical_json_bytes(snapshot_payload)).hexdigest(),
        "prev_sig_hash": prev,
        "public_key_id": signer["public_key_id"],
        "algorithm": signer["algorithm"],
    }
    payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    signature = _sign(signer, payload_sha)
    envelope = payload | {"sig_payload_sha256": payload_sha, "signature": signature}
    envelope["sig_hash"] = compute_envelope_hash(envelope, hash_field="sig_hash")
    path = root / SIGNATURE_DIR / f"sig_{safe_ts(payload['created_at'])}_snapshot.json"
    write_json(path, envelope)
    append_jsonl(root / SIGNATURE_INDEX_PATH, envelope)
    return envelope


def verify_recent_snapshots(repo_root: Path, *, last: int = 10) -> VerifyResult:
    root = repo_root.resolve()
    policy = parse_verify_policy(
        enable_env="SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY",
        last_n_env="SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY_LAST_N",
        warn_env="SENTIENTOS_ATTESTATION_SNAPSHOT_WARN",
        enforce_env="SENTIENTOS_ATTESTATION_SNAPSHOT_ENFORCE",
        default_last_n=last,
    )
    if not policy.enabled:
        return VerifyResult(ok=True, status="skipped", reason="verify_disabled", checked_n=0, last_ok_hash=None)
    rows = resolve_recent_rows(index_path=root / SIGNATURE_INDEX_PATH, sig_dir=root / SIGNATURE_DIR, sig_glob="sig_*.json", last_n=policy.last_n)
    if not rows:
        return VerifyResult(ok=True, status="skipped", reason="signature_missing", checked_n=0, last_ok_hash=None)
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return VerifyResult(ok=True, status="skipped", reason="signer_disabled", checked_n=0, last_ok_hash=None)
    prev_hash: str | None = None
    checked_n = 0
    last_ok_hash: str | None = None
    for row in rows:
        payload = {
            "schema_version": int(row.get("schema_version") or 1),
            "kind": as_str(row.get("kind")) or "",
            "object_id": as_str(row.get("object_id")) or "",
            "created_at": as_str(row.get("created_at")) or "",
            "path": as_str(row.get("path")) or "",
            "object_sha256": as_str(row.get("object_sha256")) or "",
            "prev_sig_hash": as_str(row.get("prev_sig_hash")),
            "public_key_id": as_str(row.get("public_key_id")) or "",
            "algorithm": as_str(row.get("algorithm")) or "",
        }
        payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if as_str(row.get("sig_payload_sha256")) != payload_sha:
            return _verify_fail(policy, checked_n, last_ok_hash, "sig_payload_sha_mismatch")
        if not _verify_signature(signer, payload_sha, as_str(row.get("signature")) or ""):
            return _verify_fail(policy, checked_n, last_ok_hash, "signature_invalid")
        sig_hash = as_str(row.get("sig_hash"))
        if sig_hash != compute_envelope_hash(row, hash_field="sig_hash"):
            return _verify_fail(policy, checked_n, last_ok_hash, "sig_hash_mismatch")
        if prev_hash and as_str(row.get("prev_sig_hash")) != prev_hash:
            return _verify_fail(policy, checked_n, last_ok_hash, "prev_sig_hash_mismatch")
        snapshot_payload = read_json(root / (as_str(row.get("path")) or ""))
        obj_sha = hashlib.sha256(canonical_json_bytes(snapshot_payload)).hexdigest()
        if as_str(row.get("object_sha256")) != obj_sha:
            return _verify_fail(policy, checked_n, last_ok_hash, "object_sha_mismatch")
        prev_hash = sig_hash
        checked_n += 1
        last_ok_hash = sig_hash
    return VerifyResult(ok=True, status="ok", reason=None, checked_n=checked_n, last_ok_hash=last_ok_hash)


def maybe_publish_snapshot_witness(repo_root: Path, *, allow_git_tag_publish: bool) -> tuple[dict[str, object], str | None]:
    root = repo_root.resolve()
    if os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_WITNESS_PUBLISH", "0") != "1":
        return {"status": "disabled", "published_at": None, "failure": None, "tag": None}, None
    rows = read_jsonl(root / SIGNATURE_INDEX_PATH)
    if not rows:
        return {"status": "failed", "published_at": None, "failure": "signature_missing", "tag": None}, "signature_missing"
    latest = rows[-1]
    sig_hash = as_str(latest.get("sig_hash")) or ""
    tag = f"sentientos-attestation-snapshot/{(as_str(latest.get('created_at')) or '')[:10]}/{sig_hash[:16]}"
    backend = os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_WITNESS_BACKEND", "file")
    witness = publish_witness(
        repo_root=root,
        backend=backend,
        tag=tag,
        message=f"snapshot_sig_hash: {sig_hash}",
        file_path=root / "glow/federation/attestation_snapshot_witness_tags.jsonl",
        file_row={"tag": tag, "sig_hash": sig_hash, "published_at": as_str(latest.get("created_at"))},
        allow_git_tag_publish=allow_git_tag_publish,
    )
    status = witness.to_dict()
    if witness.failure and os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_WITNESS_ENFORCE", "0") == "1":
        return status, witness.failure
    return status, None


def latest_snapshot_hashes(repo_root: Path) -> tuple[str | None, str | None]:
    root = repo_root.resolve()
    snapshots = sorted((root / SNAPSHOT_DIR).glob("snapshot_*.json"), key=lambda p: p.name)
    snapshot_hash: str | None = None
    if snapshots:
        payload = read_json(snapshots[-1])
        snapshot_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:16]
    rows = read_jsonl(root / SIGNATURE_INDEX_PATH)
    sig_hash = as_str(rows[-1].get("sig_hash"))[:16] if rows and as_str(rows[-1].get("sig_hash")) else None
    return snapshot_hash, sig_hash


def _verify_fail(policy: object, checked_n: int, last_ok_hash: str | None, reason: str) -> VerifyResult:
    enforce = getattr(policy, "enforce")
    status = "fail" if enforce else "warn"
    return VerifyResult(ok=False, status=status, reason=reason, checked_n=checked_n, last_ok_hash=last_ok_hash)


def _resolve_signer(*, require_configured: bool) -> dict[str, str] | None:
    backend = os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "off")
    if backend in {"off", "disabled", "none"}:
        if require_configured:
            raise RuntimeError("snapshot_signing_disabled")
        return None
    if backend == "hmac-test":
        secret = os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_SECRET", "snapshot-secret")
        return {"mode": backend, "secret": secret, "public_key_id": os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_HMAC_KEY_ID", "snapshot-hmac"), "algorithm": "hmac-test"}
    if backend == "ssh":
        key = Path(os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SSH_KEY", ""))
        allowed = Path(os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_ALLOWED_SIGNERS", ""))
        key_id = os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_KEY_ID", "snapshot")
        if not key or not allowed:
            raise RuntimeError("snapshot_signing_ssh_config_missing")
        return {"mode": "ssh", "key": str(key), "allowed": str(allowed), "public_key_id": key_id, "algorithm": "ssh-ed25519"}
    raise RuntimeError(f"snapshot_signing_unknown_mode:{backend}")


def _sign(signer: dict[str, str], payload_sha: str) -> str:
    if signer["mode"] == "hmac-test":
        digest = hmac.new(signer["secret"].encode("utf-8"), payload_sha.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")
    with tempfile.TemporaryDirectory(prefix="sentientos-snapshot-sign-") as tmp:
        msg = Path(tmp) / "payload.txt"
        msg.write_text(payload_sha + "\n", encoding="utf-8")
        completed = subprocess.run(["ssh-keygen", "-Y", "sign", "-n", "sentientos-attestation-snapshot", "-f", signer["key"], str(msg)], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"snapshot_ssh_sign_failed:{completed.stderr.strip()}")
        return base64.b64encode(msg.with_suffix(".txt.sig").read_bytes()).decode("ascii")


def _verify_signature(signer: dict[str, str], payload_sha: str, signature: str) -> bool:
    if signer["mode"] == "hmac-test":
        return hmac.compare_digest(_sign(signer, payload_sha), signature)
    try:
        raw_sig = base64.b64decode(signature.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return False
    with tempfile.TemporaryDirectory(prefix="sentientos-snapshot-verify-") as tmp:
        sig_path = Path(tmp) / "payload.sig"
        sig_path.write_bytes(raw_sig)
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                signer["allowed"],
                "-I",
                signer["public_key_id"],
                "-n",
                "sentientos-attestation-snapshot",
                "-s",
                str(sig_path),
            ],
            input=(payload_sha + "\n").encode("utf-8"),
            capture_output=True,
            check=False,
        )
        return completed.returncode == 0


def _latest_sig_hash(repo_root: Path) -> str | None:
    rows = read_jsonl(repo_root / SIGNATURE_INDEX_PATH)
    return as_str(rows[-1].get("sig_hash")) if rows else None

