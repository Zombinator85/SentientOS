from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

# Haptic device bridge.
#
# This module provides a thin abstraction over vendor APIs or serial
# connections for ingesting tactile feedback. Events are timestamped and
# logged to ``logs/haptics_events.jsonl``.
#
# The default implementation uses ``pyserial`` if available and otherwise falls
# back to a simple mock that generates random feedback values.

from logging_config import get_log_path

import json
import os
import random
import time
from pathlib import Path
from typing import Dict, Optional

from utils import is_headless

try:  # optional
    import serial  # type: ignore
except Exception:  # pragma: no cover - optional
    serial = None

LOG_FILE = get_log_path("haptics_events.jsonl", "HAPTIC_LOG")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


class HapticsBridge:
    """Interface to haptic devices via serial or mock."""

    def __init__(self, port: Optional[str] = None) -> None:
        require_admin_banner()
        self.headless = is_headless() or serial is None
        if not self.headless and port:
            try:
                self.ser = serial.Serial(port)
            except Exception:  # pragma: no cover - connection failure
                self.ser = None
                self.headless = True
        else:
            self.ser = None

    def read_event(self) -> Dict[str, object]:
        """Return the latest haptic event."""
        if self.ser is not None:
            try:
                line = self.ser.readline().decode("utf-8").strip()
                value = float(line)
            except Exception:  # pragma: no cover - read failure
                value = random.random()
        else:
            value = random.random()
        entry = {"timestamp": time.time(), "device": "haptic", "value": value}
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry


if __name__ == "__main__":  # pragma: no cover - manual
    bridge = HapticsBridge()
    for _ in range(5):
        print(bridge.read_event())
        time.sleep(0.5)
