"""Continuous screen awareness module with optional OCR summarisation."""
from __future__ import annotations
LEGACY_PERCEPTION_QUARANTINE = True
PULSE_COMPATIBLE_TELEMETRY = True
PERCEPTION_AUTHORITY = "none"
RAW_RETENTION_DEFAULT = False
CAN_TRIGGER_ACTIONS = False
CAN_WRITE_MEMORY = False
EMBODIMENT_RETENTION_GATE_PRESENT = True
EMBODIMENT_RETENTION_GATE_DEFAULT_MODE = "compatibility_legacy"
EMBODIMENT_RETENTION_GATE_PROPOSAL_ONLY_SUPPORTED = True
LEGACY_DIRECT_RETENTION_REQUIRES_EXPLICIT_MODE = True
MIGRATION_TARGET = "sentientos.perception_api"
NON_AUTHORITY_RATIONALE = "Legacy perception surface emits telemetry only; migration routes shaping through sentientos.perception_api."



from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from logging_config import get_log_path
from perception_journal import PerceptionJournal
from utils import is_headless
from sentientos.perception_api import emit_legacy_perception_telemetry, normalize_screen_observation
from sentientos.embodiment_fusion import build_embodiment_snapshot
from sentientos.embodiment_ingress import evaluate_embodiment_ingress, should_allow_legacy_retention_write, mark_legacy_direct_retention_preserved, build_retention_ingress_candidate

try:  # pragma: no cover - optional dependency
    import mss  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency missing
    mss = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from PIL import Image  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency missing
    Image = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    import pytesseract  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency missing
    pytesseract = None  # type: ignore[assignment]


HEADLESS = is_headless()


@dataclass
class ScreenSnapshot:
    """Serializable snapshot of what the screen looked like at a moment in time."""

    timestamp: float
    text: str
    ocr_confidence: float | None = None
    width: int | None = None
    height: int | None = None
    extras: Dict[str, str] = field(default_factory=dict)

    def summary(self, max_chars: int = 200) -> str:
        text = self.text.strip()
        if not text:
            return "screen appeared mostly graphical"
        if len(text) > max_chars:
            text = text[: max_chars - 1].rstrip() + "…"
        return text


class ScreenAwareness:
    """Capture and OCR the primary display, logging meaningful updates."""

    def __init__(
        self,
        interval: float = 1.0,
        change_threshold: int = 40,
        log_path: Optional[Path] = None,
        journal: Optional[PerceptionJournal] = None,
    ) -> None:
        self.interval = interval
        self.change_threshold = change_threshold
        self.log_path = log_path or get_log_path("multimodal/screen_awareness.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal = journal
        self._last_text: str = ""
        self._sct = None if HEADLESS else (mss.mss() if mss else None)
        self._monitor = None
        if self._sct is not None:
            monitors = getattr(self._sct, "monitors", [])
            self._monitor = monitors[1] if len(monitors) > 1 else (monitors[0] if monitors else None)

    def _capture(self) -> Optional[ScreenSnapshot]:
        if HEADLESS or self._sct is None or self._monitor is None or Image is None:
            return None
        grab = self._sct.grab(self._monitor)
        img = Image.frombytes("RGB", grab.size, grab.rgb)
        text = ""
        confidence: float | None = None
        if pytesseract is not None:
            try:
                result = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                text = " ".join(result.get("text", [])).strip()
                confidences = [int(c) for c in result.get("conf", []) if c not in {"-1", -1}]
                if confidences:
                    confidence = sum(confidences) / (len(confidences) * 100)
            except Exception:
                text = ""
                confidence = None
        snapshot = ScreenSnapshot(
            timestamp=time.time(),
            text=text,
            ocr_confidence=confidence,
            width=grab.width,
            height=grab.height,
        )
        return snapshot

    def _log_snapshot(self, snapshot: ScreenSnapshot, *, ingress_gate_mode: str = EMBODIMENT_RETENTION_GATE_DEFAULT_MODE) -> dict[str, object]:
        payload = normalize_screen_observation(timestamp=snapshot.timestamp, text=snapshot.text, ocr_confidence=snapshot.ocr_confidence, width=snapshot.width, height=snapshot.height)
        _ = emit_legacy_perception_telemetry("screen", payload, source_module="screen_awareness", legacy_quarantine=True, quarantine_risk="ocr_privacy")
        _ingress = evaluate_embodiment_ingress(build_embodiment_snapshot([_]))
        _ingress["retention_candidate"] = build_retention_ingress_candidate(build_embodiment_snapshot([_]), retention_surface="screen_ocr", source_refs=["screen", "ocr"])
        _ingress["retention_gate_mode"] = ingress_gate_mode
        _ingress["retention_risk"] = "ocr_privacy"
        if should_allow_legacy_retention_write(ingress_gate_mode):
            _ingress = mark_legacy_direct_retention_preserved(_ingress, retention_surface="screen_ocr", mode=ingress_gate_mode)
            try:
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(os.getenv("JSON_DUMP_PREFIX", "") + json.dumps(payload, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return _ingress

    def _record_journal(self, snapshot: ScreenSnapshot) -> None:
        if not self.journal:
            return
        note = snapshot.summary()
        extra = {
            "ocr_confidence": snapshot.ocr_confidence,
            "width": snapshot.width,
            "height": snapshot.height,
        }
        try:
            self.journal.record(["screen", "visual"], note, extra={k: v for k, v in extra.items() if v is not None})
        except Exception:
            pass

    def capture_once(self, *, ingress_gate_mode: str = EMBODIMENT_RETENTION_GATE_DEFAULT_MODE) -> Optional[ScreenSnapshot]:
        snapshot = self._capture()
        if snapshot is None:
            return None
        if len(snapshot.text or "") < self.change_threshold and len(self._last_text or "") < self.change_threshold:
            return None
        if snapshot.text.strip() == self._last_text.strip():
            return None
        self._last_text = snapshot.text
        _ = self._log_snapshot(snapshot, ingress_gate_mode=ingress_gate_mode)
        self._record_journal(snapshot)
        return snapshot

    def run(self, max_iterations: Optional[int] = None) -> None:
        if HEADLESS or self._sct is None:
            return
        iterations = 0
        while True:
            self.capture_once()
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(self.interval)


__all__ = ["ScreenAwareness", "ScreenSnapshot"]
