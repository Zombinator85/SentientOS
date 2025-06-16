import sys
import types

sys.modules.setdefault('dotenv', types.SimpleNamespace(load_dotenv=lambda *a, **k: None))

from gui.cathedral_gui import validate_settings, MODEL_OPTIONS

def test_openai_requires_key():
    ok, msg = validate_settings("openai/gpt-4o", "", "http://x")
    assert not ok
    assert "API" in msg


def test_valid_settings():
    ok, _ = validate_settings(MODEL_OPTIONS[0], "k", "http://x")
    assert ok


def test_invalid_endpoint():
    ok, _ = validate_settings(MODEL_OPTIONS[0], "k", "ftp://bad")
    assert not ok
