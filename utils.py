from typing import List

def chunk_message(text: str, max_len: int = 4096) -> List[str]:
    """Split text into chunks suitable for Telegram messages.

    Parameters
    ----------
    text: str
        The message to split.
    max_len: int, optional
        Maximum length of each chunk. Defaults to 4096 which is
        Telegram's maximum message size.

    Returns
    -------
    List[str]
        List of message chunks, none longer than ``max_len``. Empty
        input returns an empty list.
    """
    if max_len <= 0:
        raise ValueError("max_len must be positive")

    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + max_len])
        start += max_len
    return chunks
