from __future__ import annotations

import subprocess
import shutil
import time
import urllib.request
from pathlib import Path

import pytest

# Skip if required tools are not available
if (
    shutil.which("kind") is None
    or shutil.which("helm") is None
    or shutil.which("kubectl") is None
):
    pytest.skip("kind, helm, or kubectl not available", allow_module_level=True)


def _wait_for_status(url: str, timeout: int = 120) -> int:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url) as resp:
                return int(resp.getcode())
        except Exception:
            time.sleep(2)
    raise RuntimeError("status endpoint not available")


def test_placeholder(tmp_path: Path) -> None:
    cluster_name = "sentientos-test"
    try:
        subprocess.run(["kind", "create", "cluster", "--name", cluster_name], check=True)
        subprocess.run(["helm", "install", cluster_name, "./helm"], check=True)
        subprocess.run([
            "kubectl",
            "wait",
            "--for=condition=ready",
            "pod",
            "-l",
            "app=relay",
            "--timeout=180s",
        ], check=True)
        pf = subprocess.Popen(["kubectl", "port-forward", "service/relay", "5000:5000"])
        try:
            status = _wait_for_status("http://localhost:5000/status")
            assert status == 200
        finally:
            pf.terminate()
            pf.wait()
    finally:
        subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=False)

