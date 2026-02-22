from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Protocol

from sentientos.anchor_witness import maybe_publish_anchor_witness
from sentientos.artifact_catalog import append_catalog_entry
from sentientos.receipt_chain import RECEIPTS_DIR, RECEIPTS_INDEX_PATH, verify_receipt_chain

ANCHORS_DIR = RECEIPTS_DIR / "anchors"
ANCHORS_INDEX_PATH = ANCHORS_DIR / "anchors_index.jsonl"
ANCHOR_NAMESPACE = "sentientos-receipt-anchor"


@dataclass(slots=True)
class Anchor:
    schema_version: int
    anchor_id: str
    created_at: str
    receipt_chain_tip_hash: str
    prev_anchor_hash: str | None
    receipts_index_sha256: str | None
    anchor_payload_sha256: str
    signature: str
    public_key_id: str
    algorithm: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "anchor_id": self.anchor_id,
            "created_at": self.created_at,
            "receipt_chain_tip_hash": self.receipt_chain_tip_hash,
            "prev_anchor_hash": self.prev_anchor_hash,
            "receipts_index_sha256": self.receipts_index_sha256,
            "anchor_payload_sha256": self.anchor_payload_sha256,
            "signature": self.signature,
            "public_key_id": self.public_key_id,
            "algorithm": self.algorithm,
        }


@dataclass(slots=True)
class AnchorVerification:
    status: str
    checked_at: str
    checked_count: int
    last_anchor_id: str | None = None
    last_anchor_created_at: str | None = None
    last_anchor_tip_hash: str | None = None
    last_anchor_public_key_id: str | None = None
    failure_reason: str | None = None
    failure_detail: dict[str, object] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "checked_at": self.checked_at,
            "checked_count": self.checked_count,
            "last_anchor_id": self.last_anchor_id,
            "last_anchor_created_at": self.last_anchor_created_at,
            "last_anchor_tip_hash": self.last_anchor_tip_hash,
            "last_anchor_public_key_id": self.last_anchor_public_key_id,
        }
        if self.failure_reason:
            payload["failure_reason"] = self.failure_reason
        if self.failure_detail:
            payload["failure_detail"] = self.failure_detail
        return payload


class Signer(Protocol):
    algorithm: str
    public_key_id: str

    def sign(self, payload_sha256: str) -> str:
        ...

    def verify(self, payload_sha256: str, signature_b64: str) -> bool:
        ...


class HmacTestSigner:
    algorithm = "hmac-sha256-test"

    def __init__(self, *, secret: str, public_key_id: str) -> None:
        self._secret = secret.encode("utf-8")
        self.public_key_id = public_key_id

    def sign(self, payload_sha256: str) -> str:
        digest = hmac.new(self._secret, payload_sha256.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def verify(self, payload_sha256: str, signature_b64: str) -> bool:
        expected = self.sign(payload_sha256)
        return hmac.compare_digest(expected, signature_b64)


class SshSigner:
    algorithm = "ed25519"

    def __init__(self, *, key_path: Path, allowed_signers: Path, public_key_id: str) -> None:
        self._key_path = key_path
        self._allowed_signers = allowed_signers
        self.public_key_id = public_key_id

    def sign(self, payload_sha256: str) -> str:
        with tempfile.TemporaryDirectory(prefix="sentientos-anchor-sign-") as tmp:
            msg_path = Path(tmp) / "payload.txt"
            msg_path.write_text(payload_sha256 + "\n", encoding="utf-8")
            completed = subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-n", ANCHOR_NAMESPACE, "-f", str(self._key_path), str(msg_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"ssh_sign_failed:{completed.stderr.strip()}")
            sig_path = msg_path.with_suffix(msg_path.suffix + ".sig")
            signature = sig_path.read_bytes()
            return base64.b64encode(signature).decode("ascii")

    def verify(self, payload_sha256: str, signature_b64: str) -> bool:
        try:
            signature = base64.b64decode(signature_b64.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError):
            return False
        with tempfile.TemporaryDirectory(prefix="sentientos-anchor-verify-") as tmp:
            sig_path = Path(tmp) / "payload.sig"
            sig_path.write_bytes(signature)
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
                    ANCHOR_NAMESPACE,
                    "-s",
                    str(sig_path),
                ],
                input=(payload_sha256 + "\n").encode("utf-8"),
                capture_output=True,
                check=False,
            )
            return completed.returncode == 0


def canonical_anchor_payload_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def compute_anchor_payload_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_anchor_payload_bytes(payload)).hexdigest()


def create_anchor(repo_root: Path) -> Anchor:
    signer = _resolve_signer(require_configured=True)
    tip_hash = _latest_receipt_hash(repo_root)
    if not tip_hash:
        raise RuntimeError("anchor_create_failed:receipt_tip_missing")
    created_at = _iso_now()
    prev_anchor_hash = _latest_anchor_hash(repo_root)
    index_sha = _sha256_file(repo_root / RECEIPTS_INDEX_PATH)
    short_tip = tip_hash[:12]
    anchor_id = f"{created_at}-{short_tip}"
    payload = {
        "schema_version": 1,
        "anchor_id": anchor_id,
        "created_at": created_at,
        "receipt_chain_tip_hash": tip_hash,
        "prev_anchor_hash": prev_anchor_hash,
        "receipts_index_sha256": index_sha,
        "public_key_id": signer.public_key_id,
        "algorithm": signer.algorithm,
    }
    payload_sha = compute_anchor_payload_sha256(payload)
    signature = signer.sign(payload_sha)
    anchor = Anchor(
        schema_version=1,
        anchor_id=anchor_id,
        created_at=created_at,
        receipt_chain_tip_hash=tip_hash,
        prev_anchor_hash=prev_anchor_hash,
        receipts_index_sha256=index_sha,
        anchor_payload_sha256=payload_sha,
        signature=signature,
        public_key_id=signer.public_key_id,
        algorithm=signer.algorithm,
    )
    safe_ts = "".join(ch if ch.isalnum() else "-" for ch in created_at)
    path = repo_root / ANCHORS_DIR / f"anchor_{safe_ts}_{short_tip}.json"
    _write_json_atomic(path, anchor.to_dict())
    _append_jsonl_atomic(
        repo_root / ANCHORS_INDEX_PATH,
        {
            "anchor_id": anchor.anchor_id,
            "created_at": anchor.created_at,
            "receipt_chain_tip_hash": anchor.receipt_chain_tip_hash,
            "anchor_payload_sha256": anchor.anchor_payload_sha256,
            "public_key_id": anchor.public_key_id,
            "algorithm": anchor.algorithm,
        },
    )
    append_catalog_entry(
        repo_root,
        kind="anchor",
        artifact_id=anchor.anchor_id,
        relative_path=str(path.relative_to(repo_root)),
        schema_name="anchor",
        schema_version=anchor.schema_version,
        links={"anchor_id": anchor.anchor_id, "receipt_hash": anchor.receipt_chain_tip_hash},
        summary={"status": "created"},
        ts=anchor.created_at,
    )
    return anchor


def verify_receipt_anchors(repo_root: Path, *, last: int | None = None, require_tip: bool = False) -> AnchorVerification:
    checked_at = _iso_now()
    anchors = _load_anchor_records(repo_root)
    if not anchors:
        return AnchorVerification(status="missing", checked_at=checked_at, checked_count=0)

    chain = verify_receipt_chain(repo_root)
    if not chain.ok:
        return AnchorVerification(status="invalid", checked_at=checked_at, checked_count=0, failure_reason="receipt_chain_broken", failure_detail=chain.to_dict())

    receipt_hashes = _receipt_hashes(repo_root)
    start = max(0, len(anchors) - last) if isinstance(last, int) and last > 0 else 0
    prior_anchor_hash = _anchor_hash(anchors[start - 1]) if start > 0 else None
    signer_error: str | None = None
    for idx in range(start, len(anchors)):
        anchor = anchors[idx]
        payload_sha = _as_str(anchor.get("anchor_payload_sha256"))
        if not payload_sha:
            return _failure("anchor_payload_sha_missing", checked_at, idx - start + 1, anchor)
        payload = _anchor_payload_from_record(anchor)
        expected_sha = compute_anchor_payload_sha256(payload)
        if expected_sha != payload_sha:
            return _failure(
                "anchor_payload_sha_mismatch",
                checked_at,
                idx - start + 1,
                anchor,
                {"expected": expected_sha, "found": payload_sha},
            )
        signer, signer_error = _resolve_signer_for_anchor(anchor)
        if signer is None:
            return _failure("signing_config_invalid", checked_at, idx - start + 1, anchor, {"reason": signer_error or "unknown"})
        signature = _as_str(anchor.get("signature"))
        if not signature or not signer.verify(payload_sha, signature):
            return _failure("signature_invalid", checked_at, idx - start + 1, anchor)
        tip_hash = _as_str(anchor.get("receipt_chain_tip_hash"))
        if not tip_hash or tip_hash not in receipt_hashes:
            return _failure("anchor_tip_missing", checked_at, idx - start + 1, anchor)
        index_sha = _as_str(anchor.get("receipts_index_sha256"))
        if index_sha:
            current_index_sha = _sha256_file(repo_root / RECEIPTS_INDEX_PATH)
            if current_index_sha != index_sha:
                return _failure("receipts_index_sha_mismatch", checked_at, idx - start + 1, anchor, {"expected": index_sha, "found": current_index_sha})
        prev_anchor_hash = _as_str(anchor.get("prev_anchor_hash"))
        if prev_anchor_hash != prior_anchor_hash:
            return _failure(
                "prev_anchor_hash_mismatch",
                checked_at,
                idx - start + 1,
                anchor,
                {"expected": prior_anchor_hash, "found": prev_anchor_hash},
            )
        prior_anchor_hash = _anchor_hash(anchor)

    latest = anchors[-1]
    latest_tip = _as_str(latest.get("receipt_chain_tip_hash"))
    current_tip = _latest_receipt_hash(repo_root)
    if require_tip and latest_tip != current_tip:
        return _failure(
            "latest_anchor_not_tip",
            checked_at,
            len(anchors) - start,
            latest,
            {"expected_tip": current_tip, "anchor_tip": latest_tip},
        )
    return AnchorVerification(
        status="ok",
        checked_at=checked_at,
        checked_count=len(anchors) - start,
        last_anchor_id=_as_str(latest.get("anchor_id")),
        last_anchor_created_at=_as_str(latest.get("created_at")),
        last_anchor_tip_hash=latest_tip,
        last_anchor_public_key_id=_as_str(latest.get("public_key_id")),
    )


def maybe_verify_receipt_anchors(repo_root: Path, *, context: str, last: int = 20) -> tuple[AnchorVerification | None, bool, bool]:
    _ = context
    enforce = os.getenv("SENTIENTOS_RECEIPT_ANCHOR_ENFORCE", "0") == "1"
    warn = os.getenv("SENTIENTOS_RECEIPT_ANCHOR_WARN", "0") == "1"
    if not enforce and not warn:
        return None, False, False
    require_tip = os.getenv("SENTIENTOS_RECEIPT_ANCHOR_REQUIRE_TIP", "0") == "1"
    result = verify_receipt_anchors(repo_root, last=last, require_tip=require_tip)
    is_failure = not result.ok
    return result, enforce and is_failure, warn and not enforce and is_failure


def maybe_create_anchor_on_merge(repo_root: Path) -> tuple[Anchor | None, str | None]:
    if os.getenv("SENTIENTOS_RECEIPT_ANCHOR_ON_MERGE", "0") != "1":
        return None, None
    try:
        anchor = create_anchor(repo_root)
    except RuntimeError as exc:
        return None, str(exc)
    _status, witness_error = maybe_publish_anchor_witness(repo_root)
    if witness_error:
        return anchor, witness_error
    return anchor, None


def latest_anchor_summary(repo_root: Path) -> dict[str, object] | None:
    anchors = _load_anchor_records(repo_root)
    if not anchors:
        return None
    latest = anchors[-1]
    return {
        "anchor_id": _as_str(latest.get("anchor_id")),
        "created_at": _as_str(latest.get("created_at")),
        "tip_hash": _as_str(latest.get("receipt_chain_tip_hash")),
        "public_key_id": _as_str(latest.get("public_key_id")),
    }


def _failure(reason: str, checked_at: str, checked_count: int, anchor: dict[str, object], detail: dict[str, object] | None = None) -> AnchorVerification:
    return AnchorVerification(
        status="invalid",
        checked_at=checked_at,
        checked_count=checked_count,
        last_anchor_id=_as_str(anchor.get("anchor_id")),
        last_anchor_created_at=_as_str(anchor.get("created_at")),
        last_anchor_tip_hash=_as_str(anchor.get("receipt_chain_tip_hash")),
        last_anchor_public_key_id=_as_str(anchor.get("public_key_id")),
        failure_reason=reason,
        failure_detail=detail,
    )


def _resolve_signer(require_configured: bool) -> Signer:
    mode = os.getenv("SENTIENTOS_ANCHOR_SIGNING", "off")
    if mode == "hmac-test":
        secret = os.getenv("SENTIENTOS_ANCHOR_HMAC_SECRET", "sentientos-anchor-test-secret")
        public_key_id = os.getenv("SENTIENTOS_ANCHOR_PUBLIC_KEY_ID", "hmac-test")
        return HmacTestSigner(secret=secret, public_key_id=public_key_id)
    if mode == "ssh":
        key = os.getenv("SENTIENTOS_ANCHOR_SSH_KEY")
        allowed = os.getenv("SENTIENTOS_ANCHOR_SSH_ALLOWED_SIGNERS")
        key_id = os.getenv("SENTIENTOS_ANCHOR_PUBLIC_KEY_ID")
        if not key or not allowed or not key_id:
            raise RuntimeError("anchor_create_failed:signing_config_invalid")
        return SshSigner(key_path=Path(key), allowed_signers=Path(allowed), public_key_id=key_id)
    if require_configured:
        raise RuntimeError("anchor_create_failed:signing_disabled")
    raise RuntimeError("anchor_verify_failed:signing_disabled")


def _resolve_signer_for_anchor(anchor: dict[str, object]) -> tuple[Signer | None, str | None]:
    algorithm = _as_str(anchor.get("algorithm"))
    if algorithm == "hmac-sha256-test":
        secret = os.getenv("SENTIENTOS_ANCHOR_HMAC_SECRET", "sentientos-anchor-test-secret")
        key_id = _as_str(anchor.get("public_key_id")) or "hmac-test"
        return HmacTestSigner(secret=secret, public_key_id=key_id), None
    if algorithm == "ed25519":
        allowed = os.getenv("SENTIENTOS_ANCHOR_SSH_ALLOWED_SIGNERS")
        key_id_ssh = _as_str(anchor.get("public_key_id"))
        if not allowed or not key_id_ssh:
            return None, "ssh_allowed_signers_or_key_id_missing"
        return SshSigner(key_path=Path(os.getenv("SENTIENTOS_ANCHOR_SSH_KEY", "")), allowed_signers=Path(allowed), public_key_id=key_id_ssh), None
    return None, "unsupported_algorithm"


def _anchor_payload_from_record(record: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": _as_int(record.get("schema_version")) or 1,
        "anchor_id": record.get("anchor_id"),
        "created_at": record.get("created_at"),
        "receipt_chain_tip_hash": record.get("receipt_chain_tip_hash"),
        "prev_anchor_hash": record.get("prev_anchor_hash"),
        "receipts_index_sha256": record.get("receipts_index_sha256"),
        "public_key_id": record.get("public_key_id"),
        "algorithm": record.get("algorithm"),
    }


def _anchor_hash(record: dict[str, object]) -> str:
    return hashlib.sha256(canonical_anchor_payload_bytes(record)).hexdigest()


def _load_anchor_records(repo_root: Path) -> list[dict[str, object]]:
    anchors_dir = repo_root / ANCHORS_DIR
    records: list[dict[str, object]] = []
    for path in sorted(anchors_dir.glob("anchor_*.json"), key=lambda item: item.name):
        payload = _load_json(path)
        if payload:
            records.append(payload)
    records.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("anchor_id", ""))))
    return records


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _append_jsonl_atomic(path: Path, row: dict[str, object]) -> None:
    rows = _read_jsonl(path)
    rows.append(row)
    _write_jsonl_atomic(path, rows)


def _write_jsonl_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    tmp_path.write_text(body, encoding="utf-8")
    tmp_path.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_anchor_hash(repo_root: Path) -> str | None:
    anchors = _load_anchor_records(repo_root)
    if not anchors:
        return None
    return _anchor_hash(anchors[-1])


def _latest_receipt_hash(repo_root: Path) -> str | None:
    receipts = _receipt_hashes(repo_root)
    return receipts[-1] if receipts else None


def _receipt_hashes(repo_root: Path) -> list[str]:
    hashes: list[str] = []
    receipts_dir = repo_root / RECEIPTS_DIR
    records: list[dict[str, object]] = []
    for path in sorted(receipts_dir.glob("merge_receipt_*.json"), key=lambda item: item.name):
        payload = _load_json(path)
        if payload:
            records.append(payload)
    records.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("receipt_id", ""))))
    for record in records:
        value = _as_str(record.get("receipt_hash"))
        if value:
            hashes.append(value)
    return hashes


def _sha256_file(path: Path) -> str | None:
    try:
        body = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(body).hexdigest()


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
