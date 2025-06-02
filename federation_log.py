from logging_config import get_log_path
import os
from pathlib import Path
import ledger

LOG_PATH = get_log_path("federation_log.jsonl", "FEDERATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def add(peer: str, email: str = "", message: str = "Federation sync") -> dict:
    """Record a federation blessing entry."""
    return ledger.log_federation(peer, email, message)
