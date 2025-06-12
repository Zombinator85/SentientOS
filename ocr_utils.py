"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import os
from typing import List, Dict, Any

try:
    import cv2  # type: ignore[import-untyped]  # OpenCV optional
    import numpy as np  # type: ignore[import-untyped]  # numerical operations
except Exception:
    cv2 = None
    np = None

try:
    import pytesseract  # type: ignore[import-untyped]  # Tesseract OCR module
except Exception:
    pytesseract = None


def ocr_chat_bubbles(image_path: str) -> List[Dict[str, Any]]:
    """Detect chat bubbles in ``image_path`` and OCR each one.

    Returns a list of dicts with ``bbox`` and ``text`` keys. Works best when
    OpenCV and pytesseract are installed. On failure, returns an empty list.
    """
    if cv2 is None or np is None or pytesseract is None:
        return []
    if not os.path.exists(image_path):
        return []
    try:
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )
        cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        results: List[Dict[str, Any]] = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w * h < 1000:
                continue
            crop = gray[y : y + h, x : x + w]
            text = pytesseract.image_to_string(crop)
            results.append({"bbox": [int(x), int(y), int(x + w), int(y + h)], "text": text.strip()})
        results.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
        return results
    except Exception:
        return []
