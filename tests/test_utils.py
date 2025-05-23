import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import chunk_message


def test_chunk_message_basic():
    text = 'a ' * 50
    chunks = chunk_message(text.strip(), 20)
    assert all(len(c) <= 20 for c in chunks)
    assert ' '.join(chunks).replace('  ', ' ').strip() == text.strip()
