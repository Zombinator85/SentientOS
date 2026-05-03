"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import datetime
import json
from pathlib import Path
from typing import Optional

import memory_manager as mm
from notification import send as notify
import reflection_stream as rs
import final_approval
from sentientos.control_api import canonicalize_admission_provenance, require_request_fingerprint_match, require_self_patch_apply_authority

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


def propose_patch(note: str) -> dict:
    """Record a patch proposal without applying mutations."""

    pid = mm._hash(note + datetime.datetime.utcnow().isoformat())
    patch = {
        "id": pid,
        "note": note,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "auto": False,
        "rolled_back": False,
        "approved": False,
        "rejected": False,
        "status": "proposed",
    }
    patches = _load()
    patches.append(patch)
    _save(patches)
    return patch


def _validate_gate(
    admission_token: object | None,
    authorization: object | None,
    request_fingerprint: object | None,
) -> None:
    require_self_patch_apply_authority(admission_token, authorization)
    require_request_fingerprint_match(admission_token, request_fingerprint)


def apply_patch(
    note: str,
    *,
    admission_token: object,
    authorization: object,
    request_fingerprint: object | None = None,
) -> dict:
    """Apply a vetted patch; requires admission + authorization."""

    _validate_gate(admission_token, authorization, request_fingerprint)
    pid = mm._hash(note + datetime.datetime.utcnow().isoformat())
    patch = {
        "id": pid,
        "note": note,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "auto": False,
        "rolled_back": False,
        "approved": True,
        "rejected": False,
        "status": "applied",
        "provenance": canonicalize_admission_provenance(admission_token.provenance),
        "request_fingerprint": admission_token.request_fingerprint.value,
    }
    patches = _load()
    patches.append(patch)
    _save(patches)
    mm.append_memory(note, tags=["self_patch"], source="admitted_patch")
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
