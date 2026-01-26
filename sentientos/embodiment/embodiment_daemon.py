from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from resident_kernel import (
    KernelEpochAudit,
    KernelMisuseError,
    KernelUnauthorizedError,
    ResidentKernel,
)


_ALLOWED_EMBODIMENT_FIELDS = {
    "sensor_presence_flags",
    "sensor_health_flags",
    "actuator_output_state",
    "delta_signals",
}

_FIELD_WRITERS = {
    "sensor_presence_flags": "io_subsystem",
    "sensor_health_flags": "io_subsystem",
    "actuator_output_state": "output_controller",
    "delta_signals": "signal_aggregator",
}


@dataclass(frozen=True, slots=True)
class SimulatedEvent:
    field_group: str
    key: str
    value: bool | int

    def __post_init__(self) -> None:
        if not self.field_group or not isinstance(self.field_group, str):
            raise ValueError("field_group must be a non-empty string")
        if not self.key or not isinstance(self.key, str):
            raise ValueError("key must be a non-empty string")


class SignalSource:
    def __init__(self, batches: Sequence[Sequence[SimulatedEvent]] | None = None) -> None:
        if batches is None:
            batches = _default_batches()
        normalized = tuple(tuple(batch) for batch in batches)
        if not normalized:
            raise ValueError("SignalSource requires at least one batch")
        self._batches = normalized
        self._index = 0

    def next_batch(self) -> tuple[SimulatedEvent, ...]:
        batch = self._batches[self._index % len(self._batches)]
        self._index += 1
        return batch

    def reset(self) -> None:
        self._index = 0


class EmbodimentDaemon:
    def __init__(
        self,
        kernel: ResidentKernel,
        signal_source: SignalSource | None = None,
        *,
        epoch_writer_id: str = "embodiment_daemon",
    ) -> None:
        if not isinstance(epoch_writer_id, str) or not epoch_writer_id:
            raise ValueError("epoch_writer_id must be a non-empty string")
        self._kernel = kernel
        self._signal_source = signal_source or SignalSource()
        self._epoch_writer_id = epoch_writer_id

    def tick(self) -> KernelEpochAudit:
        with self._kernel.begin_epoch(self._epoch_writer_id) as epoch:
            self._apply_events(self._signal_source.next_batch())
        if epoch.audit_record is None:
            raise RuntimeError("Epoch audit record missing after tick")
        return epoch.audit_record

    def _apply_events(self, events: Iterable[SimulatedEvent]) -> None:
        view = self._kernel.embodiment_view()
        sensor_presence_flags = dict(view.sensor_presence_flags)
        sensor_health_flags = dict(view.sensor_health_flags)
        actuator_output_state = dict(view.actuator_output_state)
        delta_signals = dict(view.delta_signals)
        touched: set[str] = set()

        for event in events:
            if event.field_group not in _ALLOWED_EMBODIMENT_FIELDS:
                raise KernelUnauthorizedError(
                    f"Embodiment daemon cannot update '{event.field_group}'"
                )
            if event.field_group == "delta_signals":
                if not isinstance(event.value, int) or event.value < 0:
                    raise KernelMisuseError("delta_signals events require non-negative ints")
                if event.key not in delta_signals:
                    raise KernelMisuseError(
                        f"delta_signals does not recognize '{event.key}'"
                    )
                delta_signals[event.key] = delta_signals[event.key] + event.value
                touched.add("delta_signals")
                continue
            if not isinstance(event.value, bool):
                raise KernelMisuseError("sensor/actuator events require bool values")
            if event.field_group == "sensor_presence_flags":
                if event.key not in sensor_presence_flags:
                    raise KernelMisuseError(
                        f"sensor_presence_flags does not recognize '{event.key}'"
                    )
                sensor_presence_flags[event.key] = event.value
                touched.add("sensor_presence_flags")
                continue
            if event.field_group == "sensor_health_flags":
                if event.key not in sensor_health_flags:
                    raise KernelMisuseError(
                        f"sensor_health_flags does not recognize '{event.key}'"
                    )
                sensor_health_flags[event.key] = event.value
                touched.add("sensor_health_flags")
                continue
            if event.field_group == "actuator_output_state":
                if event.key not in actuator_output_state:
                    raise KernelMisuseError(
                        f"actuator_output_state does not recognize '{event.key}'"
                    )
                actuator_output_state[event.key] = event.value
                touched.add("actuator_output_state")

        if "sensor_presence_flags" in touched:
            self._kernel.update_embodiment(
                _FIELD_WRITERS["sensor_presence_flags"],
                sensor_presence_flags=sensor_presence_flags,
            )
        if "sensor_health_flags" in touched:
            self._kernel.update_embodiment(
                _FIELD_WRITERS["sensor_health_flags"],
                sensor_health_flags=sensor_health_flags,
            )
        if "actuator_output_state" in touched:
            self._kernel.update_embodiment(
                _FIELD_WRITERS["actuator_output_state"],
                actuator_output_state=actuator_output_state,
            )
        if "delta_signals" in touched:
            self._kernel.update_embodiment(
                _FIELD_WRITERS["delta_signals"],
                delta_signals=delta_signals,
            )


def _default_batches() -> Sequence[Sequence[SimulatedEvent]]:
    return (
        (
            SimulatedEvent("sensor_presence_flags", "camera", True),
            SimulatedEvent("sensor_health_flags", "camera", True),
            SimulatedEvent("actuator_output_state", "screen_active", True),
            SimulatedEvent("delta_signals", "motion_detected", 1),
        ),
        (
            SimulatedEvent("sensor_presence_flags", "mic", True),
            SimulatedEvent("sensor_health_flags", "mic", True),
            SimulatedEvent("actuator_output_state", "audio_active", True),
            SimulatedEvent("delta_signals", "audio_threshold_crossed", 2),
        ),
        (
            SimulatedEvent("sensor_presence_flags", "screen", True),
            SimulatedEvent("sensor_health_flags", "screen", True),
            SimulatedEvent("actuator_output_state", "screen_active", False),
            SimulatedEvent("delta_signals", "motion_detected", 1),
        ),
    )
