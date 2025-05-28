import json
import datetime
from pathlib import Path
import memory_manager as mm

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
    }
    patches = _load()
    patches.append(patch)
    _save(patches)
    mm.append_memory(note, tags=["self_patch"], source="auto_patch" if auto else "manual_patch")
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
            return True
    return False
