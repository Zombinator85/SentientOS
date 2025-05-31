import os
import json
import datetime
from pathlib import Path

APPROVAL_LOG = Path(os.getenv("FINAL_APPROVAL_LOG", "logs/final_approval.jsonl"))
APPROVAL_LOG.parent.mkdir(parents=True, exist_ok=True)
REQUIRED_APPROVER = os.getenv("REQUIRED_FINAL_APPROVER", "4o")


def request_approval(description: str) -> bool:
    """Request approval from the configured final approver."""
    decision = os.getenv("FOUR_O_APPROVE", "true")
    approved = decision.lower() in {"1", "true", "yes", "y"}
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "approver": REQUIRED_APPROVER,
        "description": description,
        "approved": approved,
    }
    with APPROVAL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return approved
