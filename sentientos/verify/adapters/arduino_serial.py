"""Arduino serial adapter with deterministic simulation."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from .base import Adapter


class ArduinoSerialAdapter(Adapter):
    """Adapter capable of talking to Arduino hardware or a deterministic stub."""

    name = "arduino_serial"
    deterministic = False  # Hardware path is environment dependent.

    def __init__(
        self,
        *,
        port: Optional[str] = None,
        baudrate: int = 115200,
        simulate: Optional[bool] = None,
    ) -> None:
        self._port = port or os.getenv("SENTIENTOS_ARDUINO_PORT")
        self._baudrate = baudrate
        self._simulate = simulate if simulate is not None else not bool(self._port)
        self._serial = None
        self._connected = False
        self._pin_state: Dict[int, int] = {}
        self._analog_counter = 0
        self._actions: List[Dict[str, Any]] = []

    # Public helpers -----------------------------------------------------
    @property
    def simulation_mode(self) -> bool:
        return self._simulate or self._serial is None

    @property
    def recorded_actions(self) -> List[Dict[str, Any]]:
        return list(self._actions)

    # Core adapter API ---------------------------------------------------
    def connect(self) -> None:
        if self._connected:
            return
        if self._simulate:
            self._connected = True
            return
        try:
            import serial  # type: ignore
        except Exception:
            self._simulate = True
            self._connected = True
            return
        if not self._port:
            self._simulate = True
            self._connected = True
            return
        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=1)
            self._connected = True
        except Exception:
            self._serial = None
            self._simulate = True
            self._connected = True

    def perform(self, action: Dict[str, Any]) -> None:
        if not isinstance(action, dict):
            raise TypeError("action must be a dictionary")
        if not self._connected:
            raise RuntimeError("adapter not connected")
        kind = str(action.get("kind", "")).strip()
        if not kind:
            raise ValueError("action must include a 'kind' field")
        params = dict(action)
        params.pop("kind", None)
        self._actions.append({"kind": kind, **params})
        if kind == "sleep_ms":
            delay = float(params.get("ms", 0)) / 1000.0
            if self.simulation_mode:
                return
            time.sleep(delay)
            return
        if self.simulation_mode:
            if kind == "set_pin":
                pin = int(params.get("pin", 0))
                value = 1 if params.get("value") else 0
                self._pin_state[pin] = value
            return
        if not self._serial:
            raise RuntimeError("serial connection unavailable")
        payload = json.dumps({"action": kind, "params": params}) + "\n"
        self._serial.write(payload.encode("utf-8"))

    def read(self, measure: Dict[str, Any]) -> Any:
        if not isinstance(measure, dict):
            raise TypeError("measure must be a dictionary")
        if not self._connected:
            raise RuntimeError("adapter not connected")
        kind = str(measure.get("kind", "")).strip()
        if not kind:
            raise ValueError("measure must include a 'kind' field")
        params = dict(measure)
        params.pop("kind", None)
        if self.simulation_mode:
            if kind == "temp_c":
                value = 22.0 + self._analog_counter * 0.05
            elif kind == "analog":
                pin = int(params.get("pin", 0))
                value = (pin * 37 + self._analog_counter * 5) % 1024
            elif kind == "digital":
                pin = int(params.get("pin", 0))
                value = self._pin_state.get(pin, 0)
            else:
                value = {"count": self._analog_counter, "kind": kind}
            self._analog_counter += 1
            return value
        if not self._serial:
            raise RuntimeError("serial connection unavailable")
        payload = json.dumps({"read": kind, "params": params}) + "\n"
        self._serial.write(payload.encode("utf-8"))
        response = self._serial.readline().decode("utf-8").strip()
        if not response:
            raise RuntimeError("no response from serial device")
        try:
            decoded = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid response from serial device: {response!r}") from exc
        return decoded.get("value")

    def close(self) -> None:
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._connected = False
