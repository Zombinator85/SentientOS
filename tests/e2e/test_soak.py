import json
import subprocess
from pathlib import Path


def test_mini_soak_runs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    result = subprocess.run(
        ["python", "sosctl.py", "rehearse", "--duration", "5s", "--load-profile", "low"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["cycles"] >= 2
    assert payload["load_profile"] == "low"
