from typing import List

def chunk_message(text: str, chunk_size: int = 4096) -> List[str]:
    if chunk_size <= 0:
        return [text]
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
