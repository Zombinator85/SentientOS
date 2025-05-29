import json
from pathlib import Path
import subprocess

from review_cli import annotate, suggest_edit, resolve_comment


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

