import json
from pathlib import Path
import audit_immutability as ai


def test_append_and_verify(tmp_path):
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    ai.append_entry(log, {"y": 2})
    assert ai.verify(log)
    lines = log.read_text().splitlines()
    data = json.loads(lines[0])
    data["data"]["x"] = 42
    lines[0] = json.dumps(data)
    log.write_text("\n".join(lines))
    assert not ai.verify(log)
