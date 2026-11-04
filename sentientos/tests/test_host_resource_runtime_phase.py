from __future__ import annotations

import pytest

from sentientos.control_plane_kernel import (
    AuthorityClass, ControlPlaneKernel, LifecyclePhase,
)
from sentientos.host_resource_runtime import HostResourceRuntimeCoordinator


@pytest.mark.parametrize("phase", [LifecyclePhase.RUNTIME, LifecyclePhase.MAINTENANCE])
def test_observation_admission_uses_current_kernel_phase(phase, tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(decisions_path=tmp_path / "decisions.jsonl")
    kernel.set_phase(phase, actor="host_resource_runtime_test")
    coordinator = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "runtime")

    decision = coordinator.request_admission("test-runtime-observation-" + phase.value)

    assert decision.allowed
    assert decision.current_phase is phase
    assert decision.requested_phase is phase
    assert decision.authority_class is AuthorityClass.OBSERVATION
