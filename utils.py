from typing import List


def chunk_message(text: str, size: int) -> List[str]:
    """Split a long message into chunks of at most ``size`` characters."""
    text = text or ""
    return [text[i:i + size] for i in range(0, len(text), size)]
