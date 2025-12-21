"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import datetime
import json
from pathlib import Path
from typing import Optional

from control_plane import RequestType
from control_plane.records import AuthorizationError, AuthorizationRecord
import memory_manager as mm
from notification import send as notify
import reflection_stream as rs
import task_executor
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
    admission_token: task_executor.AdmissionToken | None,
    authorization: AuthorizationRecord | None,
    request_fingerprint: task_executor.RequestFingerprint | None,
) -> None:
    if admission_token is None:
        raise AuthorizationError("admission token required for self-healing apply")
    if authorization is None:
        raise AuthorizationError("authorization required for self-healing apply")
    authorization.require(RequestType.TASK_EXECUTION)
    if admission_token.issued_by != "task_admission":
        raise AuthorizationError("admission token issuer invalid")
    if not isinstance(admission_token.provenance, task_executor.AuthorityProvenance):
        raise AuthorizationError("admission token provenance missing")
    fingerprint_value = admission_token.request_fingerprint.value
    if not isinstance(fingerprint_value, str) or len(fingerprint_value) != 64:
        raise AuthorizationError("admission token fingerprint missing")
    try:
        int(fingerprint_value, 16)
    except ValueError as exc:  # pragma: no cover - defensive
        raise AuthorizationError("admission token fingerprint missing") from exc
    if request_fingerprint is not None and request_fingerprint.value != fingerprint_value:
        raise AuthorizationError("request fingerprint mismatch for self-healing apply")


def apply_patch(
    note: str,
    *,
    admission_token: task_executor.AdmissionToken,
    authorization: AuthorizationRecord,
    request_fingerprint: task_executor.RequestFingerprint | None = None,
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
        "provenance": task_executor.canonicalise_provenance(admission_token.provenance),
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
