import logging
from typing import List

def chunk_message(text: str, chunk_size: int = 4096) -> List[str]:
    """Split a message into chunks suitable for sending via Telegram or other services.

    Args:
        text: The message to split.
        chunk_size: Maximum size of each chunk.

    Returns:
        A list of message chunks, each no longer than ``chunk_size`` characters.
    """
    if not text:
        return [""]

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        line_len = len(line)
        if current_len + line_len <= chunk_size:
            current.append(line)
            current_len += line_len
        else:
            if current:
                chunks.append("".join(current))
            # If the line itself is longer than chunk_size split hard
            while line_len > chunk_size:
                chunks.append(line[:chunk_size])
                line = line[chunk_size:]
                line_len = len(line)
            current = [line]
            current_len = line_len

    if current:
        chunks.append("".join(current))

    return chunks


def setup_logger(level: int = logging.INFO) -> None:
    """Configure basic logging with a simple formatter.

    Parameters
    ----------
    level : int, optional
        Logging level passed to ``logging.basicConfig``.
    """
    logging.basicConfig(level=level,
                        format="%(asctime)s [%(levelname)s] %(message)s")

