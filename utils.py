def chunk_message(text: str, size: int = 4096):
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
