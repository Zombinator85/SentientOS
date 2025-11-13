from __future__ import annotations

import importlib
import json
from typing import Dict

import pytest


@pytest.fixture
def cache_module(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPERIMENT_ADAPTER_CACHE", str(tmp_path / "adapter_cache.jsonl"))
    module = importlib.import_module("sentientos.verify.adapters.cache")
    importlib.reload(module)
    yield module


def test_mock_adapter_determinism():
    from sentientos.verify.adapters.mock_adapter import MockAdapter

    sequence = [
        {"kind": "temp_c"},
        {"kind": "avg_r"},
        {"kind": "avg_g"},
        {"kind": "temp_c"},
    ]

    adapter_a = MockAdapter()
    adapter_a.connect()
    outputs_a = [adapter_a.read(m) for m in sequence]
    adapter_a.perform({"kind": "set_mode", "value": "test"})
    adapter_a.close()

    adapter_b = MockAdapter()
    adapter_b.connect()
    outputs_b = [adapter_b.read(m) for m in sequence]
    adapter_b.close()

    assert outputs_a == outputs_b
    assert adapter_a.recorded_actions == [{"kind": "set_mode", "value": "test"}]


def test_arduino_adapter_simulation_mode():
    from sentientos.verify.adapters.arduino_serial import ArduinoSerialAdapter

    adapter = ArduinoSerialAdapter(simulate=True)
    adapter.connect()

    assert adapter.simulation_mode is True

    adapter.perform({"kind": "set_pin", "pin": 13, "value": 1})
    temp_first = adapter.read({"kind": "temp_c"})
    analog_first = adapter.read({"kind": "analog", "pin": 0})
    analog_second = adapter.read({"kind": "analog", "pin": 0})
    digital_value = adapter.read({"kind": "digital", "pin": 13})
    adapter.close()

    adapter_repeat = ArduinoSerialAdapter(simulate=True)
    adapter_repeat.connect()
    assert temp_first == pytest.approx(adapter_repeat.read({"kind": "temp_c"}))
    assert analog_first == adapter_repeat.read({"kind": "analog", "pin": 0})
    assert analog_second == adapter_repeat.read({"kind": "analog", "pin": 0})
    assert digital_value == 1
    assert adapter_repeat.read({"kind": "digital", "pin": 13}) == 0
    adapter_repeat.close()


def test_webcam_stub_mode():
    from sentientos.verify.adapters.webcam_opencv import WebcamAdapter

    adapter = WebcamAdapter(simulate=True)
    adapter.connect()
    adapter.perform({"kind": "warmup"})
    red_value = adapter.read({"kind": "avg_r"})
    green_value = adapter.read({"kind": "avg_g"})
    adapter.close()

    adapter_repeat = WebcamAdapter(simulate=True)
    adapter_repeat.connect()
    assert red_value == adapter_repeat.read({"kind": "avg_r"})
    assert green_value == adapter_repeat.read({"kind": "avg_g"})
    adapter_repeat.close()


def test_adapter_registry():
    from sentientos.verify.sentient_verify_loop import ADAPTERS, get_adapter

    mock_cls = get_adapter("mock")
    assert mock_cls is ADAPTERS["mock"]

    with pytest.raises(ValueError):
        get_adapter("unknown")


def test_cache_round_trip(cache_module):
    payload: Dict[str, object] = {"prompt": "hello"}
    key_1 = cache_module.cache_key("openai", "answer", payload)
    key_2 = cache_module.cache_key("openai", "answer", payload)
    assert key_1 == key_2

    assert cache_module.load_cached("openai", "answer", payload) is None

    result = {"text": "world"}
    cache_module.store_cached("openai", "answer", payload, result)
    assert cache_module.load_cached("openai", "answer", payload) == result

    cache_module.store_cached("openai", "answer", payload, {"text": "ignored"})
    assert cache_module.load_cached("openai", "answer", payload) == result

    # Ensure data persisted to disk
    cache_file = cache_module._CACHE_FILE
    contents = [json.loads(line) for line in cache_file.read_text(encoding="utf-8").splitlines() if line]
    assert contents[-1]["value"] == result
