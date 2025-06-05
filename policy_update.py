from logging_config import get_log_path
import json
import datetime
from pathlib import Path
import review_requests as rr

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
POLICY_STATE_FILE = get_log_path("policy_state.json")
AUDIT_FILE = get_log_path("policy_audit.jsonl")
POLICY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    if POLICY_STATE_FILE.exists():
        try:
            return json.loads(POLICY_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"max_context_fragments": 8}


def save_state(state: dict) -> None:
    POLICY_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def log_audit(entry: dict) -> None:
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:
    state = load_state()
    previous = state.get("max_context_fragments", 8)
    state["max_context_fragments"] = 6
    save_state(state)

    timestamp = datetime.datetime.utcnow().isoformat()
    audit_entry = {
        "timestamp": timestamp,
        "policy": "max_context_fragments",
        "previous": previous,
        "current": 6,
        "rationale": "repeated relay stalls due to context overload",
        "user": "Allen",
        "emotions": {
            "frustration": 0.6,
            "confidence": 0.9,
            "anticipation": 0.8,
        },
    }
    log_audit(audit_entry)

    review_id = rr.log_request(
        "policy_review",
        "get_context",
        "Review reduction of context fragments from 8 to 6",
        agent="Allen",
        policy="max_context_fragments",
    )

    print("Policy State:", json.dumps(state))
    print("Audit Entry:", json.dumps(audit_entry))
    print("Review Request:", json.dumps(rr.get_request(review_id)))


if __name__ == "__main__":
    main()
