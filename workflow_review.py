import os
import json
from pathlib import Path
from typing import Optional, Dict

import workflow_library as wl

REVIEW_DIR = Path(os.getenv("WORKFLOW_REVIEW_DIR", "workflows/review"))
REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def flag_for_review(name: str, before: str, after: str) -> Path:
    """Store before/after versions for manual review."""
    data = {"name": name, "before": before, "after": after}
    path = REVIEW_DIR / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_pending() -> list[str]:
    return [p.stem for p in REVIEW_DIR.glob("*.json")]


def load_review(name: str) -> Optional[Dict[str, str]]:
    fp = REVIEW_DIR / f"{name}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def accept_review(name: str) -> bool:
    fp = REVIEW_DIR / f"{name}.json"
    if fp.exists():
        fp.unlink()
        return True
    return False


def revert_review(name: str) -> bool:
    info = load_review(name)
    if not info:
        return False
    tpl = wl.get_template_path(name)
    if not tpl:
        return False
    tpl.write_text(info.get("before", ""), encoding="utf-8")
    accept_review(name)
    return True
