import textwrap

def chunk_message(text, chunk_size):
    """Split text into chunks of at most `chunk_size` characters."""
    text = text or ""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
