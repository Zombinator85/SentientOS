from pathlib import Path
import ledger

LOG_PATH = Path("logs/support_log.jsonl")


def add(name: str, message: str, amount: str = "") -> dict:
    """Record a supporter blessing in the living ledger."""
    return ledger.log_support(name, message, amount)
