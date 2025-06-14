"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import os
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, cast

import final_approval

import workflow_library as wl

REVIEW_DIR = Path(os.getenv("WORKFLOW_REVIEW_DIR", "workflows/review"))
REVIEW_DIR.mkdir(parents=True, exist_ok=True)
REVIEW_LOG = REVIEW_DIR / "review_log.jsonl"


def flag_for_review(name: str, before: str, after: str, required_votes: int = 2) -> Path:
    """Store before/after versions for manual review."""
    data = {"name": name, "before": before, "after": after, "required_votes": required_votes, "votes": {}}
    path = REVIEW_DIR / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_pending() -> list[str]:
    return [p.stem for p in REVIEW_DIR.glob("*.json")]


def load_review(name: str) -> Optional[Dict[str, Any]]:
    fp = REVIEW_DIR / f"{name}.json"
    if fp.exists():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return cast(Dict[str, Any], data)
        except Exception:
            return None
    return None


def accept_review(name: str, approvers: Optional[list[str]] = None) -> bool:
    info = load_review(name)
    desc = f"workflow {name}" if info else name
    if approvers is not None:
        ok = final_approval.request_approval(desc, approvers=approvers)
    else:
        ok = final_approval.request_approval(desc)
    if not ok:
        _log_action(name, final_approval.last_approver(), "blocked")
        return False
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


def _log_action(name: str, user: str, action: str, comment: str = "") -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "name": name,
        "user": user,
        "action": action,
        "comment": comment,
    }
    with REVIEW_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def comment_review(name: str, user: str, text: str) -> None:
    info = load_review(name) or {"name": name}
    comments: List[Dict[str, Any]] = cast(List[Dict[str, Any]], info.setdefault("comments", []))
    comments.append({
        "user": user,
        "text": text,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    })
    (REVIEW_DIR / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    _log_action(name, user, "comment", text)


def vote_review(name: str, user: str, upvote: bool = True) -> None:
    info = load_review(name) or {"name": name}
    votes: Dict[str, int] = cast(Dict[str, int], info.setdefault("votes", {}))
    votes[user] = 1 if upvote else -1
    required = int(info.get("required_votes", 2))
    (REVIEW_DIR / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    _log_action(name, user, "upvote" if upvote else "downvote")
    if sum(1 for v in votes.values() if v > 0) >= required:
        accept_review(name)
        _log_action(name, "system", "auto_accept")
