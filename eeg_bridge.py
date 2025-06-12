"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()



# EEG bridge for real or emulated headsets.
#
# This module streams raw EEG samples from supported headsets or a synthetic
# source. Each sample is timestamped and logged to ``logs/eeg_events.jsonl``.
# Band power estimates (alpha, beta, theta, gamma) are also logged.
#
# The bridge falls back to a simple random data generator if ``mne`` or
# ``brainflow`` are unavailable or if ``SENTIENTOS_HEADLESS`` is enabled.

from logging_config import get_log_path

import json
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

from utils import is_headless

try:  # optional dependencies
    import mne  # type: ignore  # optional EEG dependency
    from brainflow.board_shim import BoardShim  # type: ignore  # optional EEG dependency
except Exception:  # pragma: no cover - optional
    mne = None
    BoardShim = None

LOG_FILE = get_log_path("eeg_events.jsonl", "EEG_LOG")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


class EEGBridge:
    """Stream EEG samples from a headset or synthetic source."""

    def __init__(self, board_id: Optional[int] = None) -> None:
        self.board_id = board_id
        self.headless = is_headless() or BoardShim is None
        if not self.headless and board_id is not None:
            try:
                BoardShim.enable_dev_board_logger()
                self.board = BoardShim(board_id, {})
                self.board.prepare_session()
            except Exception:  # pragma: no cover - hardware failure
                self.board = None
                self.headless = True
        else:
            self.board = None

    def _sample(self) -> List[float]:
        if self.board is not None:
            try:
                data = self.board.get_current_board_data(1)
                return data.tolist()
            except Exception:  # pragma: no cover - hardware failure
                pass
        # fallback synthetic sample
        return [random.random() for _ in range(8)]

    def _band_power(self, data: List[float]) -> Dict[str, float]:
        if mne is None:
            return {
                "alpha": random.random(),
                "beta": random.random(),
                "theta": random.random(),
                "gamma": random.random(),
            }
        try:
            psd = mne.time_frequency.psd_array_welch([data], sfreq=250, n_fft=256)
            freqs = psd[1]
            power = psd[0][0]
            return {
                "alpha": float(power[(freqs >= 8) & (freqs <= 12)].mean()),
                "beta": float(power[(freqs >= 12) & (freqs <= 30)].mean()),
                "theta": float(power[(freqs >= 4) & (freqs <= 8)].mean()),
                "gamma": float(power[(freqs >= 30) & (freqs <= 50)].mean()),
            }
        except Exception:  # pragma: no cover - calculation failure
            return {
                "alpha": random.random(),
                "beta": random.random(),
                "theta": random.random(),
                "gamma": random.random(),
            }

    def read_sample(self) -> Dict[str, object]:
        """Return a sample with timestamp and band power."""
        raw = self._sample()
        bands = self._band_power(raw)
        entry = {"timestamp": time.time(), "raw": raw, "band_power": bands}
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def stream(self, duration: float = 5.0, interval: float = 0.5) -> None:
        """Stream samples for ``duration`` seconds."""
        end = time.time() + duration
        while time.time() < end:
            self.read_sample()
            time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover - manual run
    EEGBridge().stream()
