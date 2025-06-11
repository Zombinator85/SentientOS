import json
from pathlib import Path
import pytest
import sentientos.audit_immutability as ai


def test_append_rejects_tampered_chain(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    ai.append_entry(log, {"x": 1})
    ai.append_entry(log, {"y": 2})

    lines = log.read_text().splitlines()
    bad = json.loads(lines[-1])
    bad["prev_hash"] = "bad"
    lines[-1] = json.dumps(bad)
    log.write_text("\n".join(lines))

    with pytest.raises(ValueError):
        ai.append_entry(log, {"z": 3})
