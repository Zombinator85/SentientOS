"""SQLite schema management for the encrypted memory store."""

from __future__ import annotations

import sqlite3
from typing import Callable

__all__ = ["apply_migrations", "SCHEMA_VERSION"]


SCHEMA_VERSION = 1


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
    )
    cur = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    try:
        row = cur.fetchone()
    finally:
        cur.close()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (0,))


def _migration_1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mem_keys (
            key_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            allow_writes INTEGER NOT NULL DEFAULT 1,
            usage_count INTEGER NOT NULL DEFAULT 0,
            last_used_at TEXT,
            backend TEXT NOT NULL,
            salt BLOB
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mem_fragments (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            category TEXT NOT NULL,
            importance REAL,
            key_id TEXT NOT NULL,
            nonce BLOB NOT NULL,
            ciphertext BLOB NOT NULL,
            associated_data BLOB NOT NULL,
            FOREIGN KEY(key_id) REFERENCES mem_keys(key_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mem_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_fragments_key ON mem_fragments(key_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mem_fragments_created ON mem_fragments(created_at)"
    )


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {1: _migration_1}


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply missing migrations to ``conn`` in ascending order."""

    _ensure_version_table(conn)
    cur = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    try:
        row = cur.fetchone()
    finally:
        cur.close()
    version = int(row[0]) if row else 0
    if version >= SCHEMA_VERSION:
        return

    for target in range(version + 1, SCHEMA_VERSION + 1):
        migration = _MIGRATIONS.get(target)
        if migration is None:
            raise RuntimeError(f"Missing migration implementation for version {target}")
        migration(conn)
        conn.execute("UPDATE schema_version SET version=?", (target,))
        conn.commit()
