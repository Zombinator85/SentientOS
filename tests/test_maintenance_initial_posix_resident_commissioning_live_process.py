from __future__ import annotations

import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sentientos import maintenance_initial_posix_resident_commissioning as commissioning
from sentientos.control_plane_kernel import ControlPlaneKernel
from tests.test_maintenance_initial_posix_resident_commissioning import approval, external_approval, fixture

pytestmark = [pytest.mark.no_legacy_skip, pytest.mark.skipif(os.name != "posix", reason="POSIX process proof")]


def test_real_long_running_generation_zero_process_completes_handshake(tmp_path: Path) -> None:
    """Exercise production Popen and the real sentientosd startup gate, not a launch adapter."""
    manifest = fixture(tmp_path)
    repo = Path(str(manifest["repository_root"]))
    # Small exact repository-owned harness: it exercises the same resident
    # provenance controller and child-side gate without importing unrelated
    # optional daemon surfaces unavailable in the minimal test airlock.
    repo.joinpath("sentientosd.py").write_text(
        "import os,time\n"
        "from sentientos.maintenance_resident_runtime_adoption import MaintenanceResidentRuntimeAdoptionController,load_config,CONFIG_ENV\n"
        "from sentientos.maintenance_initial_posix_resident_commissioning import await_initial_commissioning_gate\n"
        "cfg=load_config(os.environ[CONFIG_ENV])\n"
        "p=MaintenanceResidentRuntimeAdoptionController(cfg).capture_baseline()\n"
        "await_initial_commissioning_gate(p)\n"
        "while True: time.sleep(1)\n"
    )
    with (repo / ".git/info/exclude").open("a") as handle:
        handle.write("*.py\n")
    for source in Path.cwd().glob("*.py"):
        if source.name != "sentientosd.py":
            repo.joinpath(source.name).symlink_to(source.resolve())
    for source in Path.cwd().iterdir():
        if source.is_dir() and not source.name.startswith(".") and not (repo / source.name).exists():
            with (repo / ".git/info/exclude").open("a") as handle:
                handle.write(source.name + "\n")
            repo.joinpath(source.name).symlink_to(source.resolve(), target_is_directory=True)
    with (repo / ".git/info/exclude").open("a") as handle:
        handle.write("scripts/provenance_hash_chain.py\n")
    (repo / "scripts/provenance_hash_chain.py").symlink_to(Path("scripts/provenance_hash_chain.py").resolve())
    manifest["launch_timeout_seconds"] = 15
    manifest["manifest_digest"] = commissioning.digest(manifest, "manifest_digest")
    intent = commissioning.prepare_intent(manifest)
    evidence = approval(intent, synthetic=False)
    approval_path = external_approval(manifest, evidence)
    kernel = ControlPlaneKernel(decisions_path=tmp_path / "kernel.jsonl")

    result = commissioning.commission(
        manifest, evidence, kernel=kernel, correlation_id="real-child", clock=lambda: datetime(2030, 1, 2, tzinfo=timezone.utc),
        approval_evidence_path=approval_path,
    )
    pid = int(result["launch_provenance"]["pid"])
    try:
        os.kill(pid, 0)
        root = Path(str(manifest["custody_root"]))
        ready = json.loads((root / "startup-ready.json").read_text())
        assert ready["pid"] == pid
        assert result["status"] == "initial_resident_commissioned"
        assert commissioning.verify(manifest)["status"] == "initial_resident_commissioning_verified"
    finally:
        # Test-harness authority only; the production commissioner exposes no kill API.
        os.kill(pid, signal.SIGTERM)
