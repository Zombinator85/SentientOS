"""Key management helpers for encrypted personal memory."""

from __future__ import annotations

import base64
import os
import secrets
import sqlite3
import sys
from dataclasses import dataclass
from hashlib import pbkdf2_hmac
from typing import Optional


try:  # pragma: no cover - optional dependency
    import keyring  # type: ignore
except Exception:  # pragma: no cover - we fall back to passphrase mode
    keyring = None  # type: ignore


DEFAULT_SERVICE_NAME = "SentientOS Memory"


class KeyringError(RuntimeError):
    """Raised when a key operation cannot be satisfied."""


@dataclass
class KeyRecord:
    key_id: str
    backend: str
    salt: Optional[bytes]


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat()


class KeyringBackend:
    """Coordinate platform key material and metadata bookkeeping."""

    def __init__(self, conn: sqlite3.Connection, *, service_name: str = DEFAULT_SERVICE_NAME):
        self._conn = conn
        self._service = service_name
        self._configured_backend = (os.getenv("MEM_KEY_BACKEND") or "auto").strip().lower()

    # -- public API -----------------------------------------------------

    def get_active_key_id(self) -> str:
        cur = self._conn.execute(
            "SELECT key_id FROM mem_keys WHERE allow_writes=1 ORDER BY created_at DESC LIMIT 1"
        )
        try:
            row = cur.fetchone()
        finally:
            cur.close()
        if row:
            return str(row[0])
        return self.create_new_key()

    def get_key(self, key_id: str) -> bytes:
        record = self._fetch_record(key_id)
        if not record:
            raise KeyringError(f"Unknown key: {key_id}")
        if record.backend == "passphrase":
            passphrase = os.getenv("MEM_PASSPHRASE")
            if not passphrase:
                raise KeyringError("MEM_PASSPHRASE is required for passphrase backend")
            salt = record.salt or b""
            iterations = int(os.getenv("MEM_KDF_ITERS", "200000"))
            return pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)
        if keyring is None:
            raise KeyringError("keyring module unavailable; set MEM_KEY_BACKEND=passphrase")
        secret = keyring.get_password(self._service, key_id)
        if secret is None:
            raise KeyringError(f"Key material missing from keyring for {key_id}")
        try:
            return base64.b64decode(secret.encode("ascii"))
        except Exception as exc:  # pragma: no cover - defensive
            raise KeyringError("Corrupted key material") from exc

    def create_new_key(self) -> str:
        backend = self._choose_backend()
        key_id = secrets.token_hex(16)
        created_at = _now_iso()
        salt: Optional[bytes] = None
        if backend == "passphrase":
            salt = os.urandom(16)
        else:
            if keyring is None:
                # fallback to passphrase mode transparently
                backend = "passphrase"
                salt = os.urandom(16)
        self._conn.execute(
            "INSERT INTO mem_keys (key_id, created_at, status, allow_writes, backend, salt) VALUES (?, ?, 'active', 1, ?, ?)",
            (key_id, created_at, backend, salt),
        )
        self._conn.commit()

        if backend == "passphrase":
            # no separate storage required; key derived from passphrase+salt on demand
            return key_id

        # Generate a fresh key and place it in the OS keyring.
        key_bytes = os.urandom(32)
        encoded = base64.b64encode(key_bytes).decode("ascii")
        try:
            keyring.set_password(self._service, key_id, encoded)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - environment specific
            # Roll back the DB entry to avoid dangling metadata.
            self._conn.execute("DELETE FROM mem_keys WHERE key_id=?", (key_id,))
            self._conn.commit()
            raise KeyringError(f"Failed to persist key in keyring: {exc}") from exc
        return key_id

    # -- metadata helpers ----------------------------------------------

    def mark_retiring(self, key_id: str) -> None:
        self._conn.execute(
            "UPDATE mem_keys SET status='retiring', allow_writes=0 WHERE key_id=?",
            (key_id,),
        )
        self._conn.commit()

    def mark_retired(self, key_id: str) -> None:
        self._conn.execute(
            "UPDATE mem_keys SET status='retired', allow_writes=0 WHERE key_id=?",
            (key_id,),
        )
        self._conn.commit()

    def list_keys(self) -> list[dict[str, object]]:
        cur = self._conn.execute(
            "SELECT key_id, created_at, status, usage_count, last_used_at, backend FROM mem_keys ORDER BY created_at DESC"
        )
        try:
            rows = cur.fetchall()
        finally:
            cur.close()
        return [
            {
                "key_id": str(row[0]),
                "created_at": row[1],
                "status": row[2],
                "usage_count": row[3],
                "last_used_at": row[4],
                "backend": row[5],
            }
            for row in rows
        ]

    # -- private helpers ------------------------------------------------

    def _choose_backend(self) -> str:
        backend = self._configured_backend
        if backend == "auto":
            platform = sys.platform
            if platform.startswith("win"):
                backend = "dpapi"
            elif platform == "darwin":
                backend = "keychain"
            else:
                backend = "secretservice"
        if backend in {"dpapi", "keychain", "secretservice"} and keyring is None:
            return "passphrase"
        if backend not in {"dpapi", "keychain", "secretservice", "passphrase"}:
            return "passphrase"
        return backend

    def _fetch_record(self, key_id: str) -> Optional[KeyRecord]:
        cur = self._conn.execute(
            "SELECT key_id, backend, salt FROM mem_keys WHERE key_id=?",
            (key_id,),
        )
        try:
            row = cur.fetchone()
        finally:
            cur.close()
        if not row:
            return None
        salt = row[2]
        if salt is not None and not isinstance(salt, (bytes, bytearray)):
            salt = bytes(salt)
        return KeyRecord(key_id=str(row[0]), backend=str(row[1]), salt=salt)


__all__ = [
    "KeyringBackend",
    "KeyringError",
]
