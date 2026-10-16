from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import subprocess
import tempfile

from sentientos.artifact_catalog import append_catalog_entry
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
    safe_ts,
    write_json,
)
from sentientos.private_file_custody import (
    PrivateFileCustodyError,
    list_bounded_json_names_at,
    open_private_directory,
    read_private_file_at,
)
from sentientos.windows_handle_custody import (
    WindowsHandleCustodyError,
    read_explicit_file,
    read_regular_files,
    verify_explicit_directory,
)

SNAPSHOT_DIR = Path("glow/forge/attestation/snapshots")
SNAPSHOT_PULSE_PATH = Path("pulse/attestation_snapshots.jsonl")
SIGNATURE_DIR = Path("glow/forge/attestation/signatures/attestation_snapshots")
SIGNATURE_INDEX_PATH = SIGNATURE_DIR / "signatures_index.jsonl"
MAX_SNAPSHOT_VERIFY_ITEMS = 64
MAX_SNAPSHOT_SIGNATURE_INDEX_BYTES = 1_048_576
MAX_SNAPSHOT_SIGNATURE_INDEX_ROWS = 4096
MAX_SNAPSHOT_SIGNATURE_BYTES = 65_536
MAX_ATTESTATION_SNAPSHOT_BYTES = 1_048_576


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
    rel = _snapshot_rel_path(snapshot.ts)
    payload = snapshot.to_dict()
    write_json(root / rel, payload)
    append_jsonl(root / SNAPSHOT_PULSE_PATH, payload | {"path": str(rel)})
    append_catalog_entry(
        root,
        kind="attestation_snapshot",
        artifact_id=str(snapshot.ts),
        relative_path=str(rel),
        schema_name="attestation_snapshot",
        schema_version=int(payload.get("schema_version") or 1),
        links={
            "policy_hash": payload.get("policy_hash"),
            "integrity_status_hash": payload.get("integrity_status_hash"),
            "attestation_snapshot_tip": payload.get("ts"),
            "attestation_snapshot_hash": payload.get("integrity_status_hash"),
        },
        summary={"status": "present"},
        ts=str(snapshot.ts),
    )
    return str(rel)


def should_emit_snapshot(
    repo_root: Path,
    *,
    ts: str,
    integrity_status_hash: str,
    policy_hash: str,
    goal_graph_hash: str | None,
    min_interval_seconds: int,
) -> bool:
    latest = latest_snapshot_payload(repo_root)
    if not latest:
        return True
    if as_str(latest.get("integrity_status_hash")) != integrity_status_hash:
        return True
    if as_str(latest.get("policy_hash")) != policy_hash:
        return True
    if as_str(latest.get("latest_goal_graph_hash")) != as_str(goal_graph_hash):
        return True
    latest_ts = as_str(latest.get("ts")) or ""
    if _seconds_since(latest_ts, ts) >= max(1, min_interval_seconds):
        return True
    return False


def latest_snapshot_payload(repo_root: Path) -> dict[str, object]:
    rows = read_jsonl(repo_root.resolve() / SNAPSHOT_PULSE_PATH)
    for row in reversed(rows):
        if isinstance(row, dict):
            return row
    return {}


def maybe_sign_snapshot(repo_root: Path, *, snapshot_rel_path: str, snapshot_payload: dict[str, object]) -> dict[str, object] | None:
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return None
    created_at = as_str(snapshot_payload.get("ts"))
    if (created_at is None or snapshot_rel_path != str(_snapshot_rel_path(created_at))):
        raise ValueError("snapshot_path_invalid")
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
    try:
        rows = _read_recent_snapshot_signature_rows(root, limit=min(policy.last_n, MAX_SNAPSHOT_VERIFY_ITEMS))
    except (PrivateFileCustodyError, WindowsHandleCustodyError, OSError,
            UnicodeError, ValueError, json.JSONDecodeError):
        return _verify_fail(policy, 0, None, "signature_custody_invalid")
    if not rows:
        return VerifyResult(ok=True, status="skipped", reason="signature_missing", checked_n=0, last_ok_hash=None)
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return VerifyResult(ok=True, status="skipped", reason="signer_disabled", checked_n=0, last_ok_hash=None)
    prev_hash: str | None = None
    checked_n = 0
    last_ok_hash: str | None = None
    for row in rows:
        failure_digest = _signature_row_digest(row)
        version = row.get("schema_version")
        created_at = row.get("created_at")
        object_id = row.get("object_id")
        path_text = row.get("path")
        object_sha = row.get("object_sha256")
        public_key_id = row.get("public_key_id")
        algorithm = row.get("algorithm")
        previous = row.get("prev_sig_hash")
        try:
            expected_snapshot_path = str(_snapshot_rel_path(created_at)) if isinstance(created_at, str) else None
        except ValueError:
            expected_snapshot_path = None
        if (not isinstance(version, int) or isinstance(version, bool) or version != 1
                or row.get("kind") != "attestation_snapshot"
                or not isinstance(created_at, str) or not created_at
                or object_id != created_at
                or not isinstance(path_text, str) or not isinstance(object_sha, str)
                or path_text != expected_snapshot_path
                or len(object_sha) != 64 or any(ch not in "0123456789abcdef" for ch in object_sha)
                or not isinstance(public_key_id, str) or public_key_id != signer["public_key_id"]
                or not isinstance(algorithm, str) or algorithm != signer["algorithm"]
                or (previous is not None and (not isinstance(previous, str) or len(previous) != 64
                    or any(ch not in "0123456789abcdef" for ch in previous)))):
            return _verify_fail(policy, checked_n, last_ok_hash, "signature_envelope_invalid", failure_digest)
        payload = {
            "schema_version": version,
            "kind": row["kind"],
            "object_id": object_id,
            "created_at": created_at,
            "path": path_text,
            "object_sha256": object_sha,
            "prev_sig_hash": previous,
            "public_key_id": public_key_id,
            "algorithm": algorithm,
        }
        payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if as_str(row.get("sig_payload_sha256")) != payload_sha:
            return _verify_fail(policy, checked_n, last_ok_hash, "sig_payload_sha_mismatch", failure_digest)
        if not _verify_signature(signer, payload_sha, as_str(row.get("signature")) or ""):
            return _verify_fail(policy, checked_n, last_ok_hash, "signature_invalid", failure_digest)
        sig_hash = as_str(row.get("sig_hash"))
        if sig_hash != compute_envelope_hash(row, hash_field="sig_hash"):
            return _verify_fail(policy, checked_n, last_ok_hash, "sig_hash_mismatch", failure_digest)
        if prev_hash and as_str(row.get("prev_sig_hash")) != prev_hash:
            return _verify_fail(policy, checked_n, last_ok_hash, "prev_sig_hash_mismatch", failure_digest)
        try:
            snapshot_payload = _read_snapshot_payload(root, path_text)
        except (PrivateFileCustodyError, WindowsHandleCustodyError, OSError,
                UnicodeError, ValueError, json.JSONDecodeError):
            return _verify_fail(policy, checked_n, last_ok_hash, "snapshot_custody_invalid", failure_digest)
        if snapshot_payload.get("ts") != created_at:
            return _verify_fail(policy, checked_n, last_ok_hash, "snapshot_identity_mismatch", failure_digest)
        obj_sha = hashlib.sha256(canonical_json_bytes(snapshot_payload)).hexdigest()
        if object_sha != obj_sha:
            return _verify_fail(policy, checked_n, last_ok_hash, "object_sha_mismatch", failure_digest)
        prev_hash = sig_hash
        checked_n += 1
        last_ok_hash = sig_hash
    return VerifyResult(ok=True, status="ok", reason=None, checked_n=checked_n, last_ok_hash=last_ok_hash)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def _parse_signature_rows(data: bytes) -> list[dict[str, object]]:
    if not data:
        return []
    rows: list[dict[str, object]] = []
    for line in data.splitlines():
        if not line.strip():
            continue
        value = json.loads(line.decode("utf-8"), object_pairs_hook=_strict_object)
        if not isinstance(value, dict):
            raise ValueError("signature_index_row_not_object")
        rows.append(value)
        if len(rows) > MAX_SNAPSHOT_SIGNATURE_INDEX_ROWS:
            raise ValueError("signature_index_row_limit_exceeded")
    return rows


def _read_recent_snapshot_signature_rows(root: Path, *, limit: int) -> list[dict[str, object]]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_SNAPSHOT_VERIFY_ITEMS:
        raise ValueError("signature_verification_limit_invalid")
    if os.name == "nt":
        return _read_recent_snapshot_signature_rows_windows(root, limit=limit)
    # Verify the caller's root separately so only absence of the optional
    # attestation directory is treated as a genuine no-signature state.
    root_fd = open_private_directory(root, create=False)
    os.close(root_fd)
    try:
        directory_fd = open_private_directory(root / SIGNATURE_DIR, create=False)
    except PrivateFileCustodyError as exc:
        if exc.code == "directory_root_missing":
            return []
        raise
    try:
        try:
            index = read_private_file_at(directory_fd, SIGNATURE_INDEX_PATH.name,
                max_bytes=MAX_SNAPSHOT_SIGNATURE_INDEX_BYTES, require_private_mode=False)
        except PrivateFileCustodyError as exc:
            if exc.code != "file_missing":
                raise
            index = None
        if index is not None:
            rows = _parse_signature_rows(index)
            if rows:
                return rows[-limit:]
        names = list_bounded_json_names_at(directory_fd,
            max_entries=MAX_SNAPSHOT_VERIFY_ITEMS,
            max_directory_entries=MAX_SNAPSHOT_VERIFY_ITEMS + 1024)
        selected = [name for name in names if name.startswith("sig_") and name.endswith(".json")]
        rows = []
        for name in selected[-limit:]:
            raw = read_private_file_at(directory_fd, name,
                max_bytes=MAX_SNAPSHOT_SIGNATURE_BYTES, require_private_mode=False)
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
            if not isinstance(value, dict):
                raise ValueError("signature_envelope_not_object")
            rows.append(value)
        return rows
    finally:
        os.close(directory_fd)


def _read_recent_snapshot_signature_rows_windows(root: Path, *, limit: int) -> list[dict[str, object]]:
    verify_explicit_directory(root, require_private_acl=False)
    signature_directory = root / SIGNATURE_DIR
    try:
        signature_directory.lstat()
    except FileNotFoundError:
        return []
    verify_explicit_directory(signature_directory, require_private_acl=False)
    try:
        index = read_explicit_file(root / SIGNATURE_INDEX_PATH,
            max_bytes=MAX_SNAPSHOT_SIGNATURE_INDEX_BYTES, require_private_acl=False)
    except WindowsHandleCustodyError as exc:
        if str(exc) != "explicit_file_missing":
            raise
        index = None
    if index is not None:
        rows = _parse_signature_rows(index)
        if rows:
            return rows[-limit:]
    entries = read_regular_files(signature_directory,
        max_entries=MAX_SNAPSHOT_VERIFY_ITEMS,
        max_file_bytes=MAX_SNAPSHOT_SIGNATURE_BYTES,
        max_total_bytes=MAX_SNAPSHOT_VERIFY_ITEMS * MAX_SNAPSHOT_SIGNATURE_BYTES,
        suffix=".json", require_private_acl=False)
    rows = []
    for name, raw in entries:
        if not (name.startswith("sig_") and name.endswith(".json")):
            continue
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
        if not isinstance(value, dict):
            raise ValueError("signature_envelope_not_object")
        rows.append(value)
    return rows[-limit:]


def _read_snapshot_payload(root: Path, path_text: str) -> dict[str, object]:
    path = PurePosixPath(path_text)
    prefix = tuple(SNAPSHOT_DIR.parts)
    if (path.is_absolute() or "\\" in path_text or "\x00" in path_text
            or tuple(path.parts[:-1]) != prefix or len(path.parts) != len(prefix) + 1
            or not path.name.startswith("snapshot_") or not path.name.endswith(".json")):
        raise ValueError("snapshot_path_invalid")
    if os.name == "nt":
        raw = read_explicit_file(root / Path(*path.parts),
            max_bytes=MAX_ATTESTATION_SNAPSHOT_BYTES, require_private_acl=False)
    else:
        directory_fd = open_private_directory(root / SNAPSHOT_DIR, create=False)
        try:
            raw = read_private_file_at(directory_fd, path.name,
                max_bytes=MAX_ATTESTATION_SNAPSHOT_BYTES, require_private_mode=False)
        finally:
            os.close(directory_fd)
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    if not isinstance(payload, dict):
        raise ValueError("snapshot_payload_not_object")
    return payload


def _snapshot_rel_path(timestamp: str) -> Path:
    if (not isinstance(timestamp, str) or not timestamp or len(timestamp) > 128
            or "/" in timestamp or "\\" in timestamp or "\x00" in timestamp):
        raise ValueError("snapshot_timestamp_invalid")
    return SNAPSHOT_DIR / f"snapshot_{safe_ts(timestamp)}.json"


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


def _signature_row_digest(row: dict[str, object]) -> str | None:
    try:
        return hashlib.sha256(canonical_json_bytes(row)).hexdigest()
    except (TypeError, ValueError, UnicodeError):
        return None


def _verify_fail(
    policy: object, checked_n: int, last_ok_hash: str | None, reason: str,
    failed_record_sha256: str | None = None,
) -> VerifyResult:
    enforce = getattr(policy, "enforce")
    status = "fail" if enforce else "warn"
    return VerifyResult(
        ok=False, status=status, reason=reason, checked_n=checked_n,
        last_ok_hash=last_ok_hash, failed_record_sha256=failed_record_sha256,
    )


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


def _seconds_since(previous_ts: str, current_ts: str) -> int:
    from datetime import datetime, timezone

    def _parse(value: str) -> datetime | None:
        if not value:
            return None
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    previous = _parse(previous_ts)
    current = _parse(current_ts)
    if previous is None or current is None:
        return 10**9
    return max(0, int((current - previous).total_seconds()))


def _latest_sig_hash(repo_root: Path) -> str | None:
    rows = read_jsonl(repo_root / SIGNATURE_INDEX_PATH)
    return as_str(rows[-1].get("sig_hash")) if rows else None

