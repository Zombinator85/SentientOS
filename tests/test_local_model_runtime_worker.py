from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sentientos.local_model_runtime_worker import _WORKER, _valid_runtime_resource_seconds

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize("value", [True, -0.1, float("inf"), 10 ** 1000])
def test_runtime_resource_seconds_rejects_nonfinite_or_unrepresentable_values(value: object) -> None:
    assert not _valid_runtime_resource_seconds(value)


def test_exact_runtime_worker_reports_bounded_invocation_resources(tmp_path: Path) -> None:
    artifact = tmp_path / "fixture.gguf"
    artifact.write_bytes(b"fixture-model-artifact")
    fake_runtime = tmp_path / "fake-runtime"
    fake_runtime.mkdir()
    (fake_runtime / "llama_cpp.py").write_text(
        "class Llama:\n"
        "    def __init__(self, **kwargs): pass\n"
        "    def __call__(self, prompt, **kwargs):\n"
        "        return {'choices': [{'text': 'fixture response'}]}\n",
        encoding="utf-8")
    request = {
        "type": "generate",
        "prompt": "fixture prompt",
        "history": [],
        "generation": {"max_new_tokens": 8, "temperature": 0, "top_p": 1},
    }
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(fake_runtime)

    result = subprocess.run(
        [sys.executable, "-c", _WORKER, str(artifact),
         hashlib.sha256(artifact.read_bytes()).hexdigest(), "0", "64", "2",
         "rootless_experimental"],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
        env=environment,
    )

    prefix = "SENTIENTOS_LOCAL_MODEL_WORKER="
    records = [json.loads(line[len(prefix):]) for line in result.stdout.splitlines()
               if line.startswith(prefix)]
    assert result.returncode == 0, result.stderr
    assert len(records) == 2, result.stdout + result.stderr
    generated = records[1]
    assert generated["type"] == "generated"
    assert generated["output"] == "fixture response"
    metrics = generated["invocation_resources"]
    assert metrics["schema_version"] == (
        "sentientos.llama_cpp_invocation_resource_observation:v1")
    assert metrics["wall_seconds"] >= 0
    assert metrics["user_cpu_seconds"] >= 0
    assert metrics["system_cpu_seconds"] >= 0
    if sys.platform.startswith("linux"):
        assert type(metrics["process_peak_rss_bytes"]) is int
        assert metrics["process_peak_rss_bytes"] > 0
