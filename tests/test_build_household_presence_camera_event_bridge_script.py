import json
import subprocess
import sys


def test_cli_roundtrip(tmp_path) -> None:
    inp = tmp_path / "in.json"
    out = tmp_path / "out.json"
    inp.write_text(json.dumps({"event_id": "v1", "event_type": "vehicle_detected", "zone": "exterior_security_zone", "modality": "camera", "entity_class": "vehicle", "confidence": 0.91, "metadata": {}}), encoding="utf-8")
    subprocess.run([sys.executable, "scripts/build_household_presence_camera_event_bridge.py", "normalize-event", "--input", str(inp), "--output", str(out)], check=True)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["decision"]["decision"] == "accept_as_security_event"
