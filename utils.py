from typing import List

def chunk_message(text: str, max_len: int) -> List[str]:
    words = text.split()
    chunks = []
    current = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_len and current:
            chunks.append(' '.join(current))
            current = [word]
            current_len = len(word) + 1
        else:
            current.append(word)
            current_len += len(word) + 1
    if current:
        chunks.append(' '.join(current))
    return chunks or [""]
