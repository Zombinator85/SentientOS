"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
import datetime
from pathlib import Path
from typing import Optional
import memory_manager as mm
from notification import send as notify
import reflection_stream as rs
import final_approval

PATCH_PATH = mm.MEMORY_DIR / "patches.json"
PATCH_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load() -> list[dict]:
    if PATCH_PATH.exists():
        try:
            return json.loads(PATCH_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(data: list[dict]) -> None:
    PATCH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_patch(note: str, *, auto: bool = False) -> dict:
    pid = mm._hash(note + datetime.datetime.utcnow().isoformat())
    patch = {
        "id": pid,
        "note": note,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "auto": auto,
        "rolled_back": False,
        "approved": auto,
        "rejected": False,
    }
    patches = _load()
    patches.append(patch)
    _save(patches)
    mm.append_memory(note, tags=["self_patch"], source="auto_patch" if auto else "manual_patch")
    rs.log_event("self_patch", "recovery", "apply_patch", "patched", note)
    notify("self_patch", {"id": pid, "note": note})
    return patch


def list_patches() -> list[dict]:
    return _load()


def rollback_patch(pid: str) -> bool:
    patches = _load()
    for p in patches:
        if p.get("id") == pid and not p.get("rolled_back"):
            p["rolled_back"] = True
            _save(patches)
            mm.append_memory(f"Patch {pid} rolled back", tags=["self_patch"], source="rollback")
            notify("patch_rolled_back", {"id": pid})
            return True
    return False


def approve_patch(pid: str, approvers: Optional[list[str]] = None) -> bool:
    patches = _load()
    for p in patches:
        if p.get("id") == pid:
            kwargs = {"approvers": approvers} if approvers is not None else {}
            if not final_approval.request_approval(f"patch {pid}", **kwargs):
                return False
            p["approved"] = True
            p["rejected"] = False
            _save(patches)
            notify("patch_approved", {"id": pid})
            return True
    return False


def reject_patch(pid: str) -> bool:
    patches = _load()
    for p in patches:
        if p.get("id") == pid:
            p["rejected"] = True
            p["approved"] = False
            _save(patches)
            notify("patch_rejected", {"id": pid})
            return True
    return False
