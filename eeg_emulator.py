"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()



# Synthetic EEG stream for testing pipelines.
#
# This module emits random EEG events matching the schema produced by
# :mod:`eeg_bridge` and :mod:`eeg_features`. It is useful for CI where no hardware
# is present.

import time
from typing import Iterator

from eeg_bridge import EEGBridge
from eeg_features import analyze_sample


def run(duration: float = 2.0, interval: float = 0.5) -> None:
    """Stream synthetic EEG events for ``duration`` seconds."""
    bridge = EEGBridge()
    end = time.time() + duration
    while time.time() < end:
        sample = bridge.read_sample()
        analyze_sample(sample)
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover - manual
    run()
