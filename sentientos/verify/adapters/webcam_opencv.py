"""Webcam adapter with deterministic stub mode."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .base import Adapter


class WebcamAdapter(Adapter):
    """Adapter that can capture webcam frames or provide deterministic stubs."""

    name = "webcam"
    deterministic = False

    def __init__(
        self,
        *,
        device_index: Optional[int] = None,
        simulate: Optional[bool] = None,
    ) -> None:
        self._device_index = (
            device_index
            if device_index is not None
            else int(os.getenv("SENTIENTOS_WEBCAM_INDEX", "0"))
        )
        env_stub = os.getenv("SENTIENTOS_WEBCAM_STUB")
        env_simulate = None if env_stub is None else env_stub not in {"0", "false", "FALSE"}
        self._simulate = simulate if simulate is not None else (env_simulate if env_simulate is not None else True)
        self._capture = None
        self._connected = False
        self._actions: List[Dict[str, Any]] = []
        self._frame_counter = 0

    @property
    def simulation_mode(self) -> bool:
        return self._simulate or self._capture is None

    @property
    def recorded_actions(self) -> List[Dict[str, Any]]:
        return list(self._actions)

    def connect(self) -> None:
        if self._connected:
            return
        if self._simulate:
            self._connected = True
            return
        try:
            import cv2  # type: ignore
        except Exception:
            self._simulate = True
            self._connected = True
            return
        self._capture = cv2.VideoCapture(self._device_index)
        if not self._capture or not self._capture.isOpened():
            if self._capture:
                self._capture.release()
            self._capture = None
            self._simulate = True
            self._connected = True
            return
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
        if self.simulation_mode:
            return
        if kind == "warmup":
            self._discard_frames(params.get("frames", 3))
        elif kind == "capture":
            # Capture a frame to keep parity with hardware behaviour.
            self._capture_frame()
        elif kind == "wait_for_user":
            # Non-blocking placeholder in automated environments.
            return

    def read(self, measure: Dict[str, Any]) -> Any:
        if not isinstance(measure, dict):
            raise TypeError("measure must be a dictionary")
        if not self._connected:
            raise RuntimeError("adapter not connected")
        kind = str(measure.get("kind", "")).strip()
        if not kind:
            raise ValueError("measure must include a 'kind' field")
        if self.simulation_mode:
            values = {
                "avg_r": 120 + self._frame_counter,
                "avg_g": 100 + self._frame_counter,
                "avg_b": 90 + self._frame_counter,
                "luma": 110 + self._frame_counter * 0.5,
            }
            value = values.get(kind, {"kind": kind, "frame": self._frame_counter})
            self._frame_counter += 1
            return value
        frame = self._capture_frame()
        if frame is None:
            raise RuntimeError("failed to capture frame")
        return self._compute_stat(frame, kind)

    def close(self) -> None:
        if self._capture:
            try:
                self._capture.release()
            except Exception:
                pass
        self._capture = None
        self._connected = False

    # Internal utilities -------------------------------------------------
    def _discard_frames(self, count: int) -> None:
        for _ in range(int(count)):
            if self._capture_frame() is None:
                break

    def _capture_frame(self):
        if not self._capture:
            return None
        success, frame = self._capture.read()
        if not success:
            return None
        self._frame_counter += 1
        return frame

    def _compute_stat(self, frame, kind: str) -> Any:
        try:
            import numpy as np  # type: ignore
        except Exception:
            raise RuntimeError("numpy is required for webcam statistics") from None
        if kind == "avg_r":
            return float(frame[:, :, 2].mean())
        if kind == "avg_g":
            return float(frame[:, :, 1].mean())
        if kind == "avg_b":
            return float(frame[:, :, 0].mean())
        if kind == "luma":
            return float((frame[:, :, 0] * 0.0722 + frame[:, :, 1] * 0.7152 + frame[:, :, 2] * 0.2126).mean())
        raise ValueError(f"unsupported measure kind '{kind}'")
