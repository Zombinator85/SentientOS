"""Encrypted memory storage helpers shared between services."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Iterator, Optional

try:  # pragma: no cover - optional dependency resolution
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - fallback implementations
    try:
        from nacl.bindings import (
            crypto_aead_aes256gcm_decrypt,
            crypto_aead_aes256gcm_encrypt,
        )

        class AESGCM:  # type: ignore[override]
            def __init__(self, key: bytes):
                if len(key) != 32:
                    raise ValueError("AESGCM requires 32 byte keys")
                self._key = key

            def encrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
                ad = associated_data or b""
                return crypto_aead_aes256gcm_encrypt(data, ad, nonce, self._key)

            def decrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
                ad = associated_data or b""
                return crypto_aead_aes256gcm_decrypt(data, ad, nonce, self._key)

    except Exception:  # pragma: no cover - extremely small fallback for test envs
        import hashlib
        import hmac
        from itertools import count

        class AESGCM:  # type: ignore[override]
            _TAG_LEN = 16

            def __init__(self, key: bytes):
                if len(key) != 32:
                    raise ValueError("AESGCM fallback requires 32 byte keys")
                self._key = key

            def _keystream(self, nonce: bytes, length: int) -> bytes:
                stream = bytearray()
                for counter in count():
                    if len(stream) >= length:
                        break
                    block = hashlib.sha256(self._key + nonce + counter.to_bytes(4, "big")).digest()
                    stream.extend(block)
                return bytes(stream[:length])

            def encrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
                ks = self._keystream(nonce, len(data))
                ciphertext = bytes(a ^ b for a, b in zip(data, ks))
                tag = hmac.new(self._key, (associated_data or b"") + ciphertext, hashlib.sha256).digest()
                return ciphertext + tag[: self._TAG_LEN]

            def decrypt(self, nonce: bytes, data: bytes, associated_data: bytes | None) -> bytes:
                if len(data) < self._TAG_LEN:
                    raise ValueError("ciphertext too short")
                ciphertext = data[:-self._TAG_LEN]
                tag = data[-self._TAG_LEN:]
                expected = hmac.new(self._key, (associated_data or b"") + ciphertext, hashlib.sha256).digest()
                if not hmac.compare_digest(expected[: self._TAG_LEN], tag):
                    raise ValueError("authentication failed")
                ks = self._keystream(nonce, len(ciphertext))
                return bytes(a ^ b for a, b in zip(ciphertext, ks))

import schema_migrations
from keyring_backend import KeyringBackend
from safety_log import log_event
from sentientos.storage import get_data_root


_DB_LOCK = threading.RLock()
_CONNECTION: sqlite3.Connection | None = None
_KEY_BACKEND: KeyringBackend | None = None


def _db_path() -> Path:
    override = os.getenv("MEM_DB_PATH")
    if override:
        path = Path(override)
    else:
        path = get_data_root() / "memory" / "personal_mem.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    global _CONNECTION
    with _DB_LOCK:
        if _CONNECTION is None:
            conn = sqlite3.connect(_db_path())
            conn.row_factory = sqlite3.Row
            schema_migrations.apply_migrations(conn)
            _CONNECTION = conn
        return _CONNECTION


def get_backend() -> KeyringBackend:
    global _KEY_BACKEND
    if _KEY_BACKEND is None:
        _KEY_BACKEND = KeyringBackend(get_connection())
    return _KEY_BACKEND


def is_enabled() -> bool:
    return (os.getenv("MEMORY_MODE") or "personal").lower() == "personal"


def _associated_data(entry: dict) -> bytes:
    fragment_id = entry.get("id") or ""
    created_at = entry.get("timestamp") or entry.get("created_at") or ""
    category = entry.get("category") or "event"
    importance = entry.get("importance", 0.0)
    payload = f"{fragment_id}|{created_at}|{category}|{importance}"
    return payload.encode("utf-8")


def save_fragment(entry: dict) -> None:
    if not is_enabled():
        return
    conn = get_connection()
    backend = get_backend()
    key_id = backend.get_active_key_id()
    key = backend.get_key(key_id)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    associated_data = _associated_data(entry)
    plaintext = json.dumps(entry, ensure_ascii=False).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
    created_at = entry.get("timestamp") or entry.get("created_at")
    if not created_at:
        from datetime import datetime, timezone

        created_at = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
    category = entry.get("category") or "event"
    importance = float(entry.get("importance", 0.0)) if entry.get("importance") is not None else None
    fragment_id = entry.get("id") or entry.get("fragment_id")
    if not fragment_id:
        raise ValueError("fragment id required for encrypted storage")
    with _DB_LOCK:
        conn.execute(
            """
            INSERT INTO mem_fragments (id, created_at, category, importance, key_id, nonce, ciphertext, associated_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                created_at=excluded.created_at,
                category=excluded.category,
                importance=excluded.importance,
                key_id=excluded.key_id,
                nonce=excluded.nonce,
                ciphertext=excluded.ciphertext,
                associated_data=excluded.associated_data
            """,
            (fragment_id, created_at, category, importance, key_id, nonce, ciphertext, associated_data),
        )
        conn.execute(
            "UPDATE mem_keys SET usage_count = usage_count + 1, last_used_at = ? WHERE key_id=?",
            (_associated_timestamp(), key_id),
        )
        conn.commit()


def iterate_plaintext(limit: Optional[int] = None) -> Iterator[dict]:
    if not is_enabled():
        return
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, created_at, category, importance, key_id, nonce, ciphertext, associated_data FROM mem_fragments ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    cur.close()
    count = 0
    for row in rows:
        if limit is not None and count >= limit:
            break
        entry = _decrypt_row(row)
        yield entry
        count += 1


def _decrypt_row(row: sqlite3.Row, *, override_key: Optional[bytes] = None) -> dict:
    backend = get_backend()
    key_id = row["key_id"]
    key = override_key if override_key is not None else backend.get_key(key_id)
    aesgcm = AESGCM(key)
    nonce = row["nonce"]
    ciphertext = row["ciphertext"]
    associated_data = row["associated_data"]
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
    data = json.loads(plaintext.decode("utf-8"))
    if "created_at" not in data:
        data["created_at"] = row["created_at"]
    return data


def dump_raw_rows() -> list[dict[str, object]]:
    if not is_enabled():
        return []
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, created_at, category, importance, key_id, nonce, ciphertext, associated_data FROM mem_fragments"
    )
    try:
        rows = cur.fetchall()
    finally:
        cur.close()
    return [dict(row) for row in rows]


def reencrypt_batch(old_key: str, new_key: str, batch_size: int) -> int:
    if not is_enabled():
        return 0
    conn = get_connection()
    backend = get_backend()
    cur = conn.execute(
        "SELECT id, created_at, category, importance, key_id, nonce, ciphertext, associated_data FROM mem_fragments WHERE key_id=? LIMIT ?",
        (old_key, batch_size),
    )
    rows = cur.fetchall()
    cur.close()
    if not rows:
        backend.mark_retired(old_key)
        log_event("KEY_ROTATE_OK")
        return 0
    new_key_bytes = backend.get_key(new_key)
    aesgcm = AESGCM(new_key_bytes)
    old_key_bytes = backend.get_key(old_key)
    old_cipher = AESGCM(old_key_bytes)
    updated = 0
    with _DB_LOCK:
        for row in rows:
            plaintext = old_cipher.decrypt(row["nonce"], row["ciphertext"], row["associated_data"])
            new_nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(new_nonce, plaintext, row["associated_data"])
            conn.execute(
                "UPDATE mem_fragments SET key_id=?, nonce=?, ciphertext=? WHERE id=?",
                (new_key, new_nonce, ciphertext, row["id"]),
            )
            updated += 1
        conn.commit()
    return updated


def set_meta(key: str, value: str) -> None:
    conn = get_connection()
    with _DB_LOCK:
        conn.execute(
            "INSERT INTO mem_meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()


def get_meta(key: str) -> Optional[str]:
    conn = get_connection()
    cur = conn.execute("SELECT value FROM mem_meta WHERE key=?", (key,))
    try:
        row = cur.fetchone()
    finally:
        cur.close()
    return str(row[0]) if row else None


def fragment_count() -> int:
    if not is_enabled():
        return 0
    conn = get_connection()
    cur = conn.execute("SELECT COUNT(1) FROM mem_fragments")
    try:
        count = cur.fetchone()[0]
    finally:
        cur.close()
    return int(count or 0)


def db_size_bytes() -> int:
    path = _db_path()
    if not path.exists():
        return 0
    return path.stat().st_size


def category_counts() -> dict[str, int]:
    if not is_enabled():
        return {}
    conn = get_connection()
    cur = conn.execute("SELECT category, COUNT(1) FROM mem_fragments GROUP BY category")
    rows = cur.fetchall()
    cur.close()
    return {str(row[0]): int(row[1]) for row in rows}


def _associated_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


__all__ = [
    "is_enabled",
    "save_fragment",
    "iterate_plaintext",
    "dump_raw_rows",
    "reencrypt_batch",
    "fragment_count",
    "db_size_bytes",
    "category_counts",
    "set_meta",
    "get_meta",
    "get_connection",
    "get_backend",
]
