from typing import List
import os


def is_headless() -> bool:
    """Return True if SENTIENTOS_HEADLESS is set to a truthy value."""
    val = os.getenv("SENTIENTOS_HEADLESS", "").lower()
    return val in {"1", "true", "yes"}

def chunk_message(text: str, chunk_size: int = 4096) -> List[str]:
    if chunk_size <= 0:
        return [text]
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
