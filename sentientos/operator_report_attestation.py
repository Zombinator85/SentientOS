from __future__ import annotations

import base64
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
    read_jsonl,
    resolve_recent_rows,
    safe_ts,
    write_json,
)

SIGNATURE_DIR = Path("glow/forge/operator/signatures/operator_reports")
SIGNATURE_INDEX_PATH = SIGNATURE_DIR / "signatures_index.jsonl"


def maybe_sign_operator_report(repo_root: Path, *, kind: str, report_rel_path: str, report_payload: dict[str, object]) -> dict[str, object] | None:
    signer = _resolve_signer(require_configured=False)
    if signer is None:
        return None
    root = repo_root.resolve()
    report_ts = as_str(report_payload.get("ts")) or ""
    prev_hash = _latest_sig_hash(root)
    payload = {
        "schema_version": 1,
        "kind": kind,
        "object_id": report_ts or report_rel_path,
        "created_at": report_ts,
        "path": report_rel_path,
        "object_sha256": hashlib.sha256(canonical_json_bytes(report_payload)).hexdigest(),
        "prev_sig_hash": prev_hash,
        "public_key_id": signer["public_key_id"],
        "algorithm": signer["algorithm"],
    }
    payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    signature = _sign(signer, payload_sha)
    envelope = payload | {"sig_payload_sha256": payload_sha, "signature": signature}
    envelope["sig_hash"] = compute_envelope_hash(envelope, hash_field="sig_hash")
    file_name = f"sig_{safe_ts(report_ts or 'unknown')}_{kind}.json"
    write_json(root / SIGNATURE_DIR / file_name, envelope)
    append_jsonl(root / SIGNATURE_INDEX_PATH, envelope)
    return envelope


def verify_recent_operator_reports(repo_root: Path, *, last: int = 10) -> VerifyResult:
    root = repo_root.resolve()
    policy = parse_verify_policy(
        enable_env="SENTIENTOS_OPERATOR_REPORT_VERIFY",
        last_n_env="SENTIENTOS_OPERATOR_REPORT_VERIFY_LAST_N",
        warn_env="SENTIENTOS_OPERATOR_REPORT_WARN",
        enforce_env="SENTIENTOS_OPERATOR_REPORT_ENFORCE",
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
        if payload_sha != as_str(row.get("sig_payload_sha256")):
            return _fail(policy.enforce, checked_n, last_ok_hash, "sig_payload_sha_mismatch")
        if payload["prev_sig_hash"] != prev_hash:
            return _fail(policy.enforce, checked_n, last_ok_hash, "sig_chain_broken")
        signature = as_str(row.get("signature")) or ""
        if not _verify_signature(signer, payload_sha, signature):
            return _fail(policy.enforce, checked_n, last_ok_hash, "signature_invalid")
        expected_sig_hash = compute_envelope_hash(dict(row), hash_field="sig_hash")
        if expected_sig_hash != as_str(row.get("sig_hash")):
            return _fail(policy.enforce, checked_n, last_ok_hash, "sig_hash_mismatch")
        prev_hash = as_str(row.get("sig_hash"))
        last_ok_hash = prev_hash
        checked_n += 1
    return VerifyResult(ok=True, status="ok", reason="ok", checked_n=checked_n, last_ok_hash=last_ok_hash)


def operator_signing_status(repo_root: Path) -> dict[str, object]:
    mode = os.getenv("SENTIENTOS_OPERATOR_REPORT_SIGNING", "off")
    rows = read_jsonl(repo_root.resolve() / SIGNATURE_INDEX_PATH)
    latest = rows[-1] if rows else {}
    return {
        "mode": mode,
        "verify_enabled": os.getenv("SENTIENTOS_OPERATOR_REPORT_VERIFY", "0") == "1",
        "last_sig_hash": as_str(latest.get("sig_hash")),
    }


def _fail(enforce: bool, checked_n: int, last_ok_hash: str | None, reason: str) -> VerifyResult:
    return VerifyResult(ok=False, status="fail" if enforce else "warn", reason=reason, checked_n=checked_n, last_ok_hash=last_ok_hash)


def _resolve_signer(*, require_configured: bool) -> dict[str, str] | None:
    backend = os.getenv("SENTIENTOS_OPERATOR_REPORT_SIGNING", "off")
    if backend in {"off", "disabled", "none"}:
        if require_configured:
            raise RuntimeError("operator_report_signing_disabled")
        return None
    if backend == "hmac-test":
        secret = os.getenv("SENTIENTOS_OPERATOR_REPORT_HMAC_SECRET", "operator-report-secret")
        return {
            "mode": backend,
            "secret": secret,
            "public_key_id": os.getenv("SENTIENTOS_OPERATOR_REPORT_HMAC_KEY_ID", "operator-report-hmac"),
            "algorithm": "hmac-test",
        }
    if backend == "ssh":
        key = Path(os.getenv("SENTIENTOS_OPERATOR_REPORT_SSH_KEY", ""))
        allowed = Path(os.getenv("SENTIENTOS_OPERATOR_REPORT_ALLOWED_SIGNERS", ""))
        key_id = os.getenv("SENTIENTOS_OPERATOR_REPORT_KEY_ID", "operator-report")
        if not key or not allowed:
            raise RuntimeError("operator_report_signing_ssh_config_missing")
        return {"mode": "ssh", "key": str(key), "allowed": str(allowed), "public_key_id": key_id, "algorithm": "ssh-ed25519"}
    raise RuntimeError(f"operator_report_signing_unknown_mode:{backend}")


def _sign(signer: dict[str, str], payload_sha: str) -> str:
    if signer["mode"] == "hmac-test":
        digest = hmac.new(signer["secret"].encode("utf-8"), payload_sha.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")
    with tempfile.TemporaryDirectory(prefix="sentientos-operator-report-sign-") as tmp:
        msg = Path(tmp) / "payload.txt"
        msg.write_text(payload_sha + "\n", encoding="utf-8")
        completed = subprocess.run(["ssh-keygen", "-Y", "sign", "-n", "sentientos-operator-reports", "-f", signer["key"], str(msg)], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"operator_report_ssh_sign_failed:{completed.stderr.strip()}")
        return base64.b64encode(msg.with_suffix(".txt.sig").read_bytes()).decode("ascii")


def _verify_signature(signer: dict[str, str], payload_sha: str, signature: str) -> bool:
    if signer["mode"] == "hmac-test":
        return hmac.compare_digest(_sign(signer, payload_sha), signature)
    try:
        raw_sig = base64.b64decode(signature.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return False
    with tempfile.TemporaryDirectory(prefix="sentientos-operator-report-verify-") as tmp:
        sig_path = Path(tmp) / "payload.sig"
        sig_path.write_bytes(raw_sig)
        completed = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signer["allowed"], "-I", signer["public_key_id"], "-n", "sentientos-operator-reports", "-s", str(sig_path)],
            input=(payload_sha + "\n").encode("utf-8"),
            capture_output=True,
            check=False,
        )
        return completed.returncode == 0


def _latest_sig_hash(repo_root: Path) -> str | None:
    rows = read_jsonl(repo_root / SIGNATURE_INDEX_PATH)
    return as_str(rows[-1].get("sig_hash")) if rows else None
