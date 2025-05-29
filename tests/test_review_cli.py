import json
from pathlib import Path
import subprocess
import os

from review_cli import annotate, suggest_edit, resolve_comment, set_status
import importlib
import user_profile as up


def test_annotation(tmp_path):
    sb = tmp_path / "sb.json"
    data = {"chapters": [{"chapter": 1, "text": "A"}]}
    sb.write_text(json.dumps(data))
    annotate(sb, 1, "note")
    loaded = json.loads(sb.read_text())
    assert loaded["chapters"][0]["annotations"] == ["note"]
    suggest_edit(sb, 1, "fix")
    loaded = json.loads(sb.read_text())
    assert loaded["chapters"][0]["suggestions"] == ["fix"]
    resolve_comment(sb, 1, 0)
    loaded = json.loads(sb.read_text())
    assert loaded["chapters"][0].get("annotations") == []


def test_status_and_persona(tmp_path):
    sb = tmp_path / "sb.json"
    data = {"chapters": [{"chapter": 1, "text": "A"}]}
    sb.write_text(json.dumps(data))
    set_status(sb, 1, "approved")
    loaded = json.loads(sb.read_text())
    assert loaded["chapters"][0]["status"] == "approved"
    os.environ["MEMORY_DIR"] = str(tmp_path)
    importlib.reload(up)
    up.update_profile(user="bob", persona="Lumos")
    proc = subprocess.run([
        "python",
        "review_cli.py",
        str(sb),
        "--whoami",
    ], capture_output=True, text=True)
    assert "Lumos" in proc.stdout

