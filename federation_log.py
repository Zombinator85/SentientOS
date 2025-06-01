import os
from pathlib import Path
import ledger

LOG_PATH = Path(os.getenv("FEDERATION_LOG", "logs/federation_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def add(peer: str, email: str = "", message: str = "Federation sync") -> dict:
    """Record a federation blessing entry."""
    return ledger.log_federation(peer, email, message)
