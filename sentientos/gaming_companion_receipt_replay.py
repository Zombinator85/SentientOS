"""Bounded replay guards for gaming-companion admission receipts.

The SQLite implementation persists receipt consumption across dispatcher
restarts. Callers must place its database in installation-owned storage with
appropriate OS access controls; it stores hashed identifiers, not authority
keys or receipt bodies. Receipt authenticity remains the injected verifier's
responsibility.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Protocol

from .gaming_companion_bridge import CompanionBridgeError


class AdmissionReceiptReplayGuard(Protocol):
    """Preflight and atomically consume admission receipt identifiers."""

    def preflight(self, receipt_id: str) -> None: ...

    def consume(self, receipt_id: str) -> None: ...


def _validate_receipt_id(receipt_id: str) -> None:
    if not isinstance(receipt_id, str) or not receipt_id or len(receipt_id) > 256:
        raise CompanionBridgeError("avatar_command_admission_unverified")
    try:
        receipt_id.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CompanionBridgeError("avatar_command_admission_unverified") from exc


def _receipt_key(receipt_id: str) -> str:
    return hashlib.sha256(
        b"sentientos-avatar-admission-receipt:v1:" + receipt_id.encode("utf-8")
    ).hexdigest()


class InMemoryAdmissionReceiptReplayGuard:
    """Bounded process-local guard used when no durable guard is configured."""

    def __init__(self, *, max_receipts: int = 8192) -> None:
        if isinstance(max_receipts, bool) or not isinstance(max_receipts, int) or max_receipts < 1:
            raise CompanionBridgeError("avatar_command_receipt_window_invalid")
        self._max_receipts = max_receipts
        self._receipt_keys: set[str] = set()
        self._lock = threading.Lock()

    def preflight(self, receipt_id: str) -> None:
        _validate_receipt_id(receipt_id)
        key = _receipt_key(receipt_id)
        with self._lock:
            if key in self._receipt_keys:
                raise CompanionBridgeError("avatar_command_admission_receipt_replayed")
            if len(self._receipt_keys) >= self._max_receipts:
                raise CompanionBridgeError("avatar_command_receipt_window_exhausted")

    def consume(self, receipt_id: str) -> None:
        _validate_receipt_id(receipt_id)
        key = _receipt_key(receipt_id)
        with self._lock:
            if key in self._receipt_keys:
                raise CompanionBridgeError("avatar_command_admission_receipt_replayed")
            if len(self._receipt_keys) >= self._max_receipts:
                raise CompanionBridgeError("avatar_command_receipt_window_exhausted")
            self._receipt_keys.add(key)


class SQLiteAdmissionReceiptReplayGuard:
    """SQLite-backed replay guard with atomic, bounded cross-process claims.

    The parent directory must already exist and must not be a symlink. The
    caller is responsible for ensuring that the directory is writable only by
    the intended installation identity. Each successful claim is committed
    before renderer queue delivery, preserving at-most-once behavior after an
    uncertain result or process restart.
    """

    _SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path, *, max_receipts: int = 8192,
                 timeout_seconds: float = 5.0) -> None:
        if isinstance(max_receipts, bool) or not isinstance(max_receipts, int) or max_receipts < 1:
            raise CompanionBridgeError("avatar_command_receipt_window_invalid")
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or not 0.1 <= timeout_seconds <= 30.0):
            raise CompanionBridgeError("avatar_command_receipt_store_timeout_invalid")
        try:
            path = Path(database_path)
        except (TypeError, ValueError) as exc:
            raise CompanionBridgeError("avatar_command_receipt_store_path_invalid") from exc
        if (not path.is_absolute() or not path.parent.is_dir()
                or path.parent.is_symlink() or path.is_symlink()
                or (path.exists() and not path.is_file())):
            raise CompanionBridgeError("avatar_command_receipt_store_path_invalid")
        self._path = path
        self._max_receipts = max_receipts
        self._timeout = float(timeout_seconds)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._path, timeout=self._timeout)
            connection.execute(f"PRAGMA busy_timeout = {int(self._timeout * 1000)}")
            return connection
        except sqlite3.Error as exc:
            if connection is not None:
                connection.close()
            raise CompanionBridgeError("avatar_command_receipt_store_unavailable") from exc

    def _initialize(self) -> None:
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version not in (0, self._SCHEMA_VERSION):
                    raise CompanionBridgeError("avatar_command_receipt_store_schema_unsupported")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS consumed_admission_receipts (
                        receipt_key TEXT PRIMARY KEY
                    )
                """)
                connection.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
                connection.commit()
        except CompanionBridgeError:
            raise
        except sqlite3.Error as exc:
            raise CompanionBridgeError("avatar_command_receipt_store_unavailable") from exc

    def preflight(self, receipt_id: str) -> None:
        _validate_receipt_id(receipt_id)
        key = _receipt_key(receipt_id)
        try:
            with closing(self._connect()) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM consumed_admission_receipts WHERE receipt_key = ?",
                    (key,),
                ).fetchone()
                if exists is not None:
                    raise CompanionBridgeError("avatar_command_admission_receipt_replayed")
                count = connection.execute(
                    "SELECT COUNT(*) FROM consumed_admission_receipts"
                ).fetchone()[0]
                if count >= self._max_receipts:
                    raise CompanionBridgeError("avatar_command_receipt_window_exhausted")
        except CompanionBridgeError:
            raise
        except sqlite3.Error as exc:
            raise CompanionBridgeError("avatar_command_receipt_store_unavailable") from exc

    def consume(self, receipt_id: str) -> None:
        _validate_receipt_id(receipt_id)
        key = _receipt_key(receipt_id)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                exists = connection.execute(
                    "SELECT 1 FROM consumed_admission_receipts WHERE receipt_key = ?",
                    (key,),
                ).fetchone()
                if exists is not None:
                    raise CompanionBridgeError("avatar_command_admission_receipt_replayed")
                count = connection.execute(
                    "SELECT COUNT(*) FROM consumed_admission_receipts"
                ).fetchone()[0]
                if count >= self._max_receipts:
                    raise CompanionBridgeError("avatar_command_receipt_window_exhausted")
                connection.execute(
                    "INSERT INTO consumed_admission_receipts (receipt_key) VALUES (?)",
                    (key,),
                )
                connection.commit()
        except CompanionBridgeError:
            raise
        except sqlite3.Error as exc:
            raise CompanionBridgeError("avatar_command_receipt_store_unavailable") from exc