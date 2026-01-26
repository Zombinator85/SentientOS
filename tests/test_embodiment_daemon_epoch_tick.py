import pytest

from resident_kernel import (
    KernelUnauthorizedError,
    KernelWriteOutsideEpochError,
    ResidentKernel,
)
from sentientos.embodiment.embodiment_daemon import (
    EmbodimentDaemon,
    SignalSource,
    SimulatedEvent,
)


def _set_kernel_ready(kernel: ResidentKernel) -> None:
    with kernel.begin_epoch("governance_arbiter"):
        kernel.update_governance("governance_arbiter", system_phase="ready")


def test_embodiment_tick_advances_epoch_and_records_audit() -> None:
    kernel = ResidentKernel()
    _set_kernel_ready(kernel)

    source = SignalSource(
        batches=[
            (
                SimulatedEvent("sensor_presence_flags", "camera", True),
                SimulatedEvent("sensor_health_flags", "camera", True),
                SimulatedEvent("actuator_output_state", "screen_active", True),
                SimulatedEvent("delta_signals", "motion_detected", 1),
            )
        ]
    )
    daemon = EmbodimentDaemon(kernel, source)

    audit = daemon.tick()

    assert audit.epoch_id == kernel.governance_view().kernel_epoch
    assert audit.validation_passed is True
    assert "sensor_presence_flags" in audit.fields_touched
    assert "sensor_health_flags" in audit.fields_touched
    assert "actuator_output_state" in audit.fields_touched
    assert "delta_signals" in audit.fields_touched

    embodiment = kernel.embodiment_view()
    assert embodiment.sensor_presence_flags["camera"] is True
    assert embodiment.sensor_health_flags["camera"] is True
    assert embodiment.actuator_output_state["screen_active"] is True
    assert embodiment.delta_signals["motion_detected"] == 1


def test_embodiment_updates_fail_outside_epoch() -> None:
    kernel = ResidentKernel()
    presence = dict(kernel.embodiment_view().sensor_presence_flags)

    with pytest.raises(KernelWriteOutsideEpochError):
        kernel.update_embodiment("io_subsystem", sensor_presence_flags=presence)


def test_embodiment_daemon_cannot_write_governance_fields() -> None:
    kernel = ResidentKernel()
    _set_kernel_ready(kernel)

    source = SignalSource(
        batches=[(SimulatedEvent("system_phase", "ready", True),)]
    )
    daemon = EmbodimentDaemon(kernel, source)

    with pytest.raises(KernelUnauthorizedError):
        daemon.tick()


def test_simulated_event_stream_is_deterministic() -> None:
    left = SignalSource()
    right = SignalSource()

    left_batches = [left.next_batch() for _ in range(3)]
    right_batches = [right.next_batch() for _ in range(3)]

    assert left_batches == right_batches
