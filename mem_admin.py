"""Administrative helpers for encrypted personal memory."""

from __future__ import annotations

from datetime import datetime, timezone
from safety_log import log_event
import secure_memory_storage as storage


def _now() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()


def rotate_keys(reencrypt_batch: int = 500) -> dict[str, object]:
    if not storage.is_enabled():
        return {"rotated": False, "reason": "secure_store_disabled"}
    backend = storage.get_backend()
    old_key = backend.get_active_key_id()
    new_key = backend.create_new_key()
    if old_key == new_key:
        return {"rotated": False, "reason": "no_prior_key"}
    backend.mark_retiring(old_key)
    updated = storage.reencrypt_batch(old_key, new_key, reencrypt_batch)
    storage.set_meta("last_rotation_at", _now())
    log_event("KEY_ROTATE_OK")
    return {
        "rotated": True,
        "new_key": new_key,
        "old_key": old_key,
        "reencrypted": updated,
    }


def list_keys() -> list[dict[str, object]]:
    if not storage.is_enabled():
        return []
    backend = storage.get_backend()
    return backend.list_keys()


def retire_key(key_id: str) -> bool:
    if not storage.is_enabled():
        return False
    backend = storage.get_backend()
    backend.mark_retiring(key_id)
    log_event("KEY_RETIRE_QUEUED")
    return True


def reflect(reencrypt_batch: int = 250) -> int:
    if not storage.is_enabled():
        return 0
    backend = storage.get_backend()
    conn = storage.get_connection()
    cur = conn.execute("SELECT key_id FROM mem_keys WHERE status='retiring'")
    keys = [str(row[0]) for row in cur.fetchall()]
    cur.close()
    total = 0
    for key_id in keys:
        new_key = backend.get_active_key_id()
        total += storage.reencrypt_batch(key_id, new_key, reencrypt_batch)
    if total:
        storage.set_meta("last_reflection_at", _now())
    return total


__all__ = ["rotate_keys", "list_keys", "retire_key", "reflect"]
