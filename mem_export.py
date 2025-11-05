"""Encrypted export/import helpers for personal memory archives."""

from __future__ import annotations

import base64
import json
import os
from hashlib import pbkdf2_hmac
from pathlib import Path
from typing import Sequence

from safety_log import log_event
import secure_memory_storage as storage
from secure_memory_storage import AESGCM

try:  # pragma: no cover - optional dependency
    import zstandard as zstd

    def _compress(data: bytes) -> tuple[bytes, str]:
        return zstd.ZstdCompressor(level=6).compress(data), "zstd"

    def _decompress(data: bytes) -> bytes:
        return zstd.ZstdDecompressor().decompress(data)

except Exception:  # pragma: no cover - fallback for environments without zstd
    import zlib

    def _compress(data: bytes) -> tuple[bytes, str]:
        return zlib.compress(data, level=6), "zlib"

    def _decompress(data: bytes) -> bytes:
        return zlib.decompress(data)


ARCHIVE_VERSION = 1


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def _derive_passphrase_key(passphrase: str, salt: bytes) -> bytes:
    iterations = int(os.getenv("MEM_KDF_ITERS", "200000"))
    return pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)


def _normalise_path(path: str | os.PathLike[str] | None) -> Path | None:
    if path is None:
        return None
    return Path(path)


def _filter_rows(rows: Sequence[dict], *, include_insights: bool, include_dreams: bool) -> list[dict]:
    categories: set[str] = set()
    if include_insights:
        categories.add("insight")
    if include_dreams:
        categories.add("dream")
    if not categories:
        return [row for row in rows if row.get("category") not in {"insight", "dream"}]
    filtered: list[dict] = []
    for row in rows:
        category = row.get("category")
        if category in categories or category not in {"insight", "dream"}:
            filtered.append(row)
    return filtered


def export_encrypted(
    path: str | os.PathLike[str] | None,
    *,
    include_insights: bool = True,
    include_dreams: bool = True,
    passphrase: str | None = None,
) -> bytes:
    if not storage.is_enabled():
        return b""
    if passphrase is None:
        passphrase = os.getenv("MEM_EXPORT_PASSPHRASE") or None
    rows = storage.dump_raw_rows()
    rows = _filter_rows(rows, include_insights=include_insights, include_dreams=include_dreams)
    backend = storage.get_backend()
    source_key_ids = sorted({row.get("key_id") for row in rows})
    entries: list[dict[str, object]] = []
    mode = "native"
    salt_bytes = b""
    derived_key: bytes | None = None
    if passphrase:
        mode = "passphrase"
        salt_bytes = os.urandom(16)
        derived_key = _derive_passphrase_key(passphrase, salt_bytes)
        exporter = AESGCM(derived_key)
    for row in rows:
        payload = {
            "id": row["id"],
            "created_at": row["created_at"],
            "category": row["category"],
            "importance": row["importance"],
            "associated_data": base64.b64encode(row["associated_data"]).decode("ascii"),
        }
        nonce = row["nonce"]
        ciphertext = row["ciphertext"]
        key_id = row["key_id"]
        if derived_key is not None:
            old_key = backend.get_key(key_id)
            plaintext = AESGCM(old_key).decrypt(nonce, ciphertext, row["associated_data"])
            new_nonce = os.urandom(12)
            ciphertext = exporter.encrypt(new_nonce, plaintext, row["associated_data"])
            payload["nonce"] = base64.b64encode(new_nonce).decode("ascii")
            payload["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
            payload["key_id"] = "export-passphrase"
        else:
            payload["nonce"] = base64.b64encode(nonce).decode("ascii")
            payload["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
            payload["key_id"] = key_id
        entries.append(payload)
    body_bytes = json.dumps({"entries": entries}, ensure_ascii=False).encode("utf-8")
    compressed, compression = _compress(body_bytes)
    header = {
        "version": ARCHIVE_VERSION,
        "created_at": _now_iso(),
        "mode": mode,
        "compression": compression,
        "key_ids": source_key_ids,
        "include_insights": include_insights,
        "include_dreams": include_dreams,
    }
    if salt_bytes:
        header["salt"] = base64.b64encode(salt_bytes).decode("ascii")
    header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")
    archive = len(header_bytes).to_bytes(4, "big") + header_bytes + compressed
    dest = _normalise_path(path)
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive)
    log_event("EXPORT_OK")
    return archive


def import_encrypted(
    payload: bytes | str | os.PathLike[str],
    *,
    merge: bool = True,
    passphrase: str | None = None,
) -> dict[str, int]:
    if not storage.is_enabled():
        return {"imported": 0}
    try:
        if isinstance(payload, (str, os.PathLike)):
            payload = Path(payload).read_bytes()
        buffer = memoryview(payload)
        if len(buffer) < 4:
            raise ValueError("Invalid archive: missing header length")
        header_len = int.from_bytes(buffer[:4], "big")
        header_bytes = bytes(buffer[4 : 4 + header_len])
        header = json.loads(header_bytes.decode("utf-8"))
        body = bytes(buffer[4 + header_len :])
        data = json.loads(_decompress(body).decode("utf-8"))
        entries = data.get("entries", [])
        mode = header.get("mode", "native")
        salt = header.get("salt")
        if mode == "passphrase":
            passphrase = passphrase or os.getenv("MEM_EXPORT_PASSPHRASE")
            if not passphrase:
                raise ValueError("Passphrase required to import this archive")
            if not salt:
                raise ValueError("Archive missing salt for passphrase mode")
            salt_bytes = base64.b64decode(salt)
            key = _derive_passphrase_key(passphrase, salt_bytes)
            decryptor = AESGCM(key)
        else:
            decryptor = None
        imported = 0
        backend = storage.get_backend()
        for row in entries:
            associated = base64.b64decode(row["associated_data"])
            nonce = base64.b64decode(row["nonce"])
            ciphertext = base64.b64decode(row["ciphertext"])
            if decryptor is not None:
                plaintext = decryptor.decrypt(nonce, ciphertext, associated)
            else:
                key = backend.get_key(row["key_id"])
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated)
            entry = json.loads(plaintext.decode("utf-8"))
            storage.save_fragment(entry)
            imported += 1
    except Exception:
        log_event("IMPORT_FAIL")
        raise
    log_event("IMPORT_OK")
    return {"imported": imported}


__all__ = ["export_encrypted", "import_encrypted"]
