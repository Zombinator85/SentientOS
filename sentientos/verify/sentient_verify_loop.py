"""Experiment execution helpers that dispatch to adapters."""
from __future__ import annotations

from collections.abc import Iterable as IterableABC
from contextlib import suppress
from typing import Any, Dict, Tuple, Type

from .adapters.base import Adapter
from .adapters import arduino_serial, mock_adapter, webcam_opencv

ADAPTERS: Dict[str, Type[Adapter]] = {
    "mock": mock_adapter.MockAdapter,
    "arduino_serial": arduino_serial.ArduinoSerialAdapter,
    "webcam": webcam_opencv.WebcamAdapter,
}


def get_adapter(name: str) -> Type[Adapter]:
    """Return the adapter class registered for *name*."""

    try:
        return ADAPTERS[name]
    except KeyError as exc:
        available = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unknown adapter '{name}'. Available adapters: {available}") from exc


def _normalise_sequence(value: Any) -> IterableABC[Dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, IterableABC) and not isinstance(value, (str, bytes)):
        result = []
        for item in value:
            if not isinstance(item, dict):
                raise TypeError("adapter configuration expects dictionaries")
            result.append(item)
        return result
    raise TypeError("adapter configuration expects a dict or iterable of dicts")


def _resolve_adapter_spec(experiment: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    spec = experiment.get("adapter")
    if isinstance(spec, str):
        return spec, {}
    if isinstance(spec, dict):
        name = spec.get("name", "mock")
        config = dict(spec.get("config", {}))
        return str(name), config
    adapters = experiment.get("adapters")
    if adapters:
        for item in _normalise_sequence(adapters):
            name = item.get("name") or item.get("adapter")
            if name:
                config = dict(item.get("config", {}))
                return str(name), config
    return "mock", {}


def execute_experiment_with_adapter(experiment: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an experiment by delegating to the configured adapter."""

    adapter_name, adapter_config = _resolve_adapter_spec(experiment)
    adapter_cls = get_adapter(adapter_name)
    adapter = adapter_cls(**adapter_config)
    adapter.connect()
    measurements: Dict[str, Any] = {}
    try:
        for action in _normalise_sequence(experiment.get("actions")):
            adapter.perform(action)
        # legacy singular action field support
        singular_action = experiment.get("action")
        if isinstance(singular_action, dict):
            adapter.perform(singular_action)
        for measure in _normalise_sequence(experiment.get("measures")):
            alias = measure.get("as") or measure.get("name") or measure.get("kind")
            if not alias:
                raise ValueError("measure definitions must include 'kind' or alias")
            measurements[str(alias)] = adapter.read(measure)
        singular_measure = experiment.get("measure")
        if isinstance(singular_measure, dict):
            alias = singular_measure.get("as") or singular_measure.get("name") or singular_measure.get("kind")
            if not alias:
                raise ValueError("measure definitions must include 'kind' or alias")
            measurements[str(alias)] = adapter.read(singular_measure)
    finally:
        adapter.close()
    context: Dict[str, Any] = dict(measurements)
    context["adapter_name"] = adapter_cls.name
    context["adapter_deterministic"] = bool(adapter_cls.deterministic)
    with suppress(AttributeError):
        context.setdefault("adapter_simulation", bool(adapter.simulation_mode))
    mock_context = experiment.get("mock_context")
    if isinstance(mock_context, dict):
        for key, value in mock_context.items():
            context.setdefault(key, value)
    # TODO: consensus gating for non-deterministic adapters.
    return context
