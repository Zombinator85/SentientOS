from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import subprocess
import threading
from pathlib import Path
from queue import Queue
from typing import Optional

POLL_INTERVAL = 5
THRESHOLD = 85
RECOVERY_TEMP = 80
THROTTLE_FLAG = Path("/pulse/throttle_active")


def _read_gpu_temperature() -> Optional[float]:
    """Return the current GPU temperature in Celsius if available."""
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        temp = pynvml.nvmlDeviceGetTemperature(
            handle, pynvml.NVML_TEMPERATURE_GPU
        )
        return float(temp)
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
                "-i",
                "0",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return float(out.splitlines()[0])
    except Exception:
        pass
    try:
        import psutil

        temps = psutil.sensors_temperatures()
        for sensor in temps.values():
            for entry in sensor:
                if "gpu" in entry.label.lower() or "gpu" in entry.sensor.lower():
                    return float(entry.current)
    except Exception:
        pass
    return None


def run_loop(
    stop: threading.Event, ledger_queue: Queue, poll_interval: int = POLL_INTERVAL
) -> None:
    temp = _read_gpu_temperature()
    if temp is None:
        ledger_queue.put({"event": "thermal_daemon_init", "status": "no_gpu_detected"})
        return
    throttled = False
    while not stop.is_set():
        if temp > THRESHOLD and not throttled:
            THROTTLE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            THROTTLE_FLAG.write_text("1", encoding="utf-8")
            ledger_queue.put(
                {
                    "event": "thermal_throttle",
                    "gpu_temp": temp,
                    "action": "throttled",
                }
            )
            throttled = True
        elif temp < RECOVERY_TEMP and throttled:
            try:
                THROTTLE_FLAG.unlink()
            except FileNotFoundError:
                pass
            ledger_queue.put({"event": "thermal_recover", "gpu_temp": temp})
            throttled = False
        if stop.wait(poll_interval):
            break
        temp = _read_gpu_temperature()
