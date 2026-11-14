from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from sentientos.local_model_runtime_worker import (
    ExactRuntimeLocalModel, _WORKER, _valid_runtime_resource_seconds,
)
from sentientos.local_model_resource_profile import LLAMA_CPP_RESOURCE_PROFILE_SCHEMA

pytestmark = pytest.mark.no_legacy_skip


def test_exact_runtime_worker_reports_confirmed_process_cancellation() -> None:
    class Process:
        returncode = None
        killed = False

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self, *, timeout):
            assert timeout == 5
            return self.returncode

    model = object.__new__(ExactRuntimeLocalModel)
    process = Process()
    model._process = process

    assert model.cancel_pending_generation() is True
    assert process.killed is True
    assert model.cancel_pending_generation() is False


def test_exact_runtime_worker_samples_cpu_before_cancellation(tmp_path, monkeypatch):
    class Process:
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def wait(self, *, timeout):
            assert timeout == 5
            return self.returncode

    model = object.__new__(ExactRuntimeLocalModel)
    model._process = Process()
    model._active_generation_started_at = time.monotonic() - 0.8
    model._active_generation_cpu_baseline = (1.0, 0.2)
    model._cancelled_generation_resources = None
    samples = iter(((1.6, 0.35),))
    monkeypatch.setattr(ExactRuntimeLocalModel, "_process_cpu_times",
        lambda self: next(samples))

    assert model.cancel_pending_generation() is True
    observation = model.take_cancelled_generation_resource_observation()
    assert observation is not None
    assert observation["observation_source"] == "parent_sampled_exact_runtime_worker"
    assert observation["user_cpu_seconds"] == pytest.approx(0.6)
    assert observation["system_cpu_seconds"] == pytest.approx(0.15)
    assert observation["wall_seconds"] >= 0.8
    assert observation["process_peak_rss_bytes"] is None
    assert model.take_cancelled_generation_resource_observation() is None


def test_exact_runtime_worker_close_waits_for_live_process_exit() -> None:
    process = subprocess.Popen(
        [sys.executable, "-u", "-c",
         "import sys\n"
         "print('ready', flush=True)\n"
         "for line in sys.stdin:\n"
         "    if line.strip() == '{\"type\":\"shutdown\"}':\n"
         "        print('shutdown', flush=True)\n"
         "        break\n"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    model = object.__new__(ExactRuntimeLocalModel)
    model._process = process
    try:
        assert process.stdout is not None
        assert process.stdout.readline() == "ready\n"
        assert process.poll() is None

        model.close()

        assert process.wait(timeout=1) == 0
        assert process.poll() == 0
        model.close()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=1)


@pytest.mark.parametrize("value", [True, -0.1, float("inf"), 10 ** 1000])
def test_runtime_resource_seconds_rejects_nonfinite_or_unrepresentable_values(value: object) -> None:
    assert not _valid_runtime_resource_seconds(value)


@pytest.mark.parametrize("fail_generation", [False, True])
@pytest.mark.parametrize("thread_ceiling,effective_threads", [(1, 1), (2, 2), (8, 2)])
def test_exact_runtime_worker_reports_bounded_invocation_resources_and_restores_threads(
        tmp_path: Path, fail_generation: bool, thread_ceiling: int,
        effective_threads: int) -> None:
    artifact = tmp_path / "fixture.gguf"
    artifact.write_bytes(b"fixture-model-artifact")
    fake_runtime = tmp_path / "fake-runtime"
    fake_runtime.mkdir()
    (fake_runtime / "llama_cpp.py").write_text(
        "import json, os\n"
        "thread_calls = []\n"
        "def llama_set_n_threads(context, threads, batch_threads):\n"
        "    thread_calls.append([threads, batch_threads])\n"
        "    open(os.environ['SENTIENTOS_THREAD_CAPTURE'], 'w').write(json.dumps(thread_calls))\n"
        "class Llama:\n"
        "    def __init__(self, **kwargs):\n"
        "        self.ctx = object()\n"
        "        self.n_threads = kwargs.get('n_threads', 4)\n"
        "        self.n_threads_batch = kwargs.get('n_threads_batch', 2)\n"
        "        open(os.environ['SENTIENTOS_PROFILE_CAPTURE'], 'w').write(json.dumps(kwargs))\n"
        "    def __call__(self, prompt, **kwargs):\n"
        "        if os.environ.get('SENTIENTOS_FAIL_GENERATION') == '1': raise RuntimeError('fixture failure')\n"
        "        return {'choices': [{'text': 'fixture response'}]}\n",
        encoding="utf-8")
    request = {
        "type": "generate",
        "prompt": "fixture prompt",
        "history": [],
        "generation": {"max_new_tokens": 8, "temperature": 0, "top_p": 1,
                       "max_backend_threads": thread_ceiling},
    }
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(fake_runtime)
    captured_options = tmp_path / "llama-options.json"
    environment["SENTIENTOS_PROFILE_CAPTURE"] = str(captured_options)
    captured_thread_calls = tmp_path / "thread-calls.json"
    environment["SENTIENTOS_THREAD_CAPTURE"] = str(captured_thread_calls)
    if fail_generation:
        environment["SENTIENTOS_FAIL_GENERATION"] = "1"
    profile = {
        "schema_version": LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
        "profile_id": "cpu-gaming-v1", "n_ctx": 64, "n_gpu_layers": 0,
        "n_threads": 4, "n_threads_batch": 2, "n_batch": 128, "n_ubatch": 64,
    }

    result = subprocess.run(
        [sys.executable, "-c", _WORKER, str(artifact),
         hashlib.sha256(artifact.read_bytes()).hexdigest(), "0", "64", "2",
         "rootless_experimental", json.dumps(profile)],
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
    assert result.returncode == (70 if fail_generation else 0), result.stderr
    assert len(records) == 2, result.stdout + result.stderr
    generated = records[1]
    if fail_generation:
        assert generated["type"] == "error"
        assert generated["diagnostic"] == "fixture failure"
    else:
        assert generated["type"] == "generated"
        assert generated["output"] == "fixture response"
        assert generated["backend_thread_limit_control"] == {
            "schema_version": "sentientos.llama_cpp_backend_thread_limit_control:v1",
            "requested_ceiling": thread_ceiling,
            "setter_function": "llama_set_n_threads",
            "n_threads_argument": effective_threads,
            "n_threads_batch_argument": effective_threads,
        }
    assert json.loads(captured_options.read_text(encoding="utf-8")) == {
        "n_ctx": 64, "n_gpu_layers": 0, "n_batch": 128, "n_ubatch": 64,
        "n_threads": 4, "n_threads_batch": 2,
        "model_path": str(artifact), "verbose": False,
    }
    assert json.loads(captured_thread_calls.read_text(encoding="utf-8")) == [
        [effective_threads, effective_threads], [4, 2]]
    if fail_generation:
        return
    metrics = generated["invocation_resources"]
    assert metrics["schema_version"] == (
        "sentientos.llama_cpp_invocation_resource_observation:v1")
    assert metrics["wall_seconds"] >= 0
    assert metrics["user_cpu_seconds"] >= 0
    assert metrics["system_cpu_seconds"] >= 0
    if sys.platform.startswith("linux"):
        assert type(metrics["process_peak_rss_bytes"]) is int
        assert metrics["process_peak_rss_bytes"] > 0


@pytest.mark.parametrize("thread_ceiling,expected_diagnostic", [
    (2, "backend_thread_limit_unavailable"),
    (None, "backend_thread_ceiling_invalid"),
])
def test_exact_runtime_worker_fails_closed_for_invalid_or_unavailable_thread_limit(
        tmp_path: Path, thread_ceiling: object, expected_diagnostic: str) -> None:
    artifact = tmp_path / "fixture.gguf"
    artifact.write_bytes(b"fixture-model-artifact")
    fake_runtime = tmp_path / "fake-runtime"
    fake_runtime.mkdir()
    (fake_runtime / "llama_cpp.py").write_text(
        "class Llama:\n"
        "    n_threads = 4\n"
        "    n_threads_batch = 4\n"
        "    ctx = object()\n"
        "    def __init__(self, **kwargs): pass\n"
        "    def __call__(self, prompt, **kwargs): raise AssertionError('must not generate')\n",
        encoding="utf-8")
    request = {"type": "generate", "prompt": "fixture prompt", "history": [],
        "generation": {"max_new_tokens": 8, "temperature": 0, "top_p": 1,
            "max_backend_threads": thread_ceiling}}
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(fake_runtime)

    result = subprocess.run(
        [sys.executable, "-c", _WORKER, str(artifact),
         hashlib.sha256(artifact.read_bytes()).hexdigest(), "0", "64", "2",
         "rootless_experimental", ""],
        input=json.dumps(request) + "\n", text=True, capture_output=True,
        check=False, timeout=10, env=environment)

    prefix = "SENTIENTOS_LOCAL_MODEL_WORKER="
    records = [json.loads(line[len(prefix):]) for line in result.stdout.splitlines()
               if line.startswith(prefix)]
    assert result.returncode == 70, result.stderr
    assert records[-1]["type"] == "error"
    assert records[-1]["diagnostic"] == expected_diagnostic
