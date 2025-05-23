import os
import sys
import pytest

# Ensure local utils.py is imported instead of any installed package
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from utils import chunk_message

def test_no_split_needed():
    text = "hello"
    assert chunk_message(text, 10) == ["hello"]

def test_exact_limit():
    text = "a" * 5
    assert chunk_message(text, 5) == ["a" * 5]

def test_split_simple():
    text = "abcdef"
    assert chunk_message(text, 4) == ["abcd", "ef"]

def test_empty_string():
    assert chunk_message("", 10) == []

def test_invalid_limit():
    with pytest.raises(ValueError):
        chunk_message("abc", 0)
