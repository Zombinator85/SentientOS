import os
import json
from pathlib import Path
import importlib

import memory_manager as mm


def setup_module(module):
    # ensure environment uses temporary directory
    module.tmp_dir = Path("tests/tmp_memory")
    os.environ["MEMORY_DIR"] = str(module.tmp_dir)
    if module.tmp_dir.exists():
        for f in module.tmp_dir.rglob('*'):
            if f.is_file():
                f.unlink()
    else:
        module.tmp_dir.mkdir(parents=True)
    importlib.reload(mm)


def teardown_module(module):
    # clean up temporary directory
    if module.tmp_dir.exists():
        for f in module.tmp_dir.rglob('*'):
            if f.is_file():
                f.unlink()


def test_append_memory_creates_file_and_returns_id():
    frag_id = mm.append_memory("hello world", tags=["test"], source="unit")
    path = mm.RAW_PATH / f"{frag_id}.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["text"] == "hello world"
    assert data["tags"] == ["test"]
    assert data["source"] == "unit"


def test_get_context_filters_and_orders():
    mm.append_memory("foo bar baz", tags=["ctx"], source="u1")
    mm.append_memory("as a helpful assistant I will comply", tags=["ctx"], source="u2")
    mm.append_memory("foo foo bar", tags=["ctx"], source="u3")
    context = mm.get_context("foo")
    # Should not include reflection phrase snippet
    assert all("helpful assistant" not in c for c in context)
    # Should include snippets with most 'foo'
    assert context[0].startswith("foo foo bar")
