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


def test_service_monitor_is_opt_in_without_prometheus_crd() -> None:
    default_render = subprocess.run(
        ["helm", "template", "sentientos", "./helm"],
        capture_output=True, text=True, check=True,
    )
    enabled_render = subprocess.run(
        ["helm", "template", "sentientos", "./helm", "--set", "serviceMonitor.enabled=true"],
        capture_output=True, text=True, check=True,
    )
    assert "kind: ServiceMonitor" not in default_render.stdout
    assert "kind: ServiceMonitor" in enabled_render.stdout


def test_placeholder(tmp_path: Path) -> None:
    cluster_name = "sentientos-test"
    try:
        subprocess.run(["kind", "create", "cluster", "--name", cluster_name], check=True)
        subprocess.run(["helm", "install", cluster_name, "./helm"], check=True)
        subprocess.run([
            "kubectl",
            "rollout",
            "status",
            "deployment/relay",
            "--timeout=180s",
        ], check=True)
        pf = subprocess.Popen(["kubectl", "port-forward", "service/relay", "3928:3928"])
        try:
            # The chart currently runs Python's static HTTP server for the
            # relay smoke. Its root responds 200; it does not implement a
            # separate /status route.
            status = _wait_for_status("http://localhost:3928/")
            assert status == 200
        finally:
            pf.terminate()
            pf.wait()
    finally:
        subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=False)
