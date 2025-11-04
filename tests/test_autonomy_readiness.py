from __future__ import annotations

import json

import tools.autonomy_readiness as readiness


def test_autonomy_readiness_pass(tmp_path, monkeypatch) -> None:
    model_root = tmp_path / "models"
    (model_root / "whisper").mkdir(parents=True)
    (model_root / "llm").mkdir(parents=True)
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("SENTIENTOS_MODEL_ROOT", str(model_root))
    monkeypatch.setenv("SENTIENTOS_REPORT_DIR", str(reports_dir))
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))

    called = {}

    def fake_which(cmd: str) -> str | None:
        mapping = {
            "arecord": "/usr/bin/arecord",
            "espeak": "/usr/bin/espeak",
            "tesseract": "/usr/bin/tesseract",
            "chromium": "/usr/bin/chromium",
            "xdotool": "/usr/bin/xdotool",
        }
        called[cmd] = True
        return mapping.get(cmd)

    monkeypatch.setattr(readiness.shutil, "which", fake_which)

    class DummyModel:
        metadata = {"engine": "diagnostic"}

        def generate(self, prompt: str, history=None, **kwargs):
            return "diagnostic llm output"

    monkeypatch.setattr(readiness, "_load_local_model", lambda: DummyModel())

    exit_code = readiness.main(["--json"])
    assert exit_code == 0
    report = json.loads((reports_dir / "autonomy_readiness.json").read_text(encoding="utf-8"))
    statuses = {name: data["status"] for name, data in report["subsystems"].items()}
    assert set(statuses.values()) == {"PASS"}
    assert "arecord" in called


def test_autonomy_readiness_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTIENTOS_MODEL_ROOT", str(tmp_path / "missing"))
    monkeypatch.setenv("SENTIENTOS_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(readiness.shutil, "which", lambda _: None)
    monkeypatch.setattr(readiness, "_load_local_model", lambda: None)
    exit_code = readiness.main(["--quiet"])
    assert exit_code == 1

