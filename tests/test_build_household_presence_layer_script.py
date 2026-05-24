import json, subprocess, sys

def test_build_and_summary_and_validate(tmp_path) -> None:
    out = tmp_path / "layer.json"
    subprocess.run([sys.executable, "scripts/build_household_presence_layer.py", "build-default", "--output", str(out)], check=True)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["metadata_only"]
    s = subprocess.run([sys.executable, "scripts/build_household_presence_layer.py", "summarize", "--input", str(out)], check=True, capture_output=True, text=True)
    assert "rule_count" in s.stdout
    v = subprocess.run([sys.executable, "scripts/build_household_presence_layer.py", "validate", "--input", str(out)], capture_output=True, text=True)
    assert v.returncode == 0
