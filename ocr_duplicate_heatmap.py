from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Generate heatmap image from OCR log data with bbox positions."""
from logging_config import get_log_path
import json
import os
from pathlib import Path

try:
    from PIL import Image  # type: ignore  # Pillow missing stubs
    import numpy as np  # type: ignore  # numpy optional for heatmap
except Exception:  # pragma: no cover - optional
    Image = None
    np = None

LOG = get_log_path("ocr_relay.jsonl", "OCR_RELAY_LOG")


def generate_heatmap(out_path: Path, width: int = 1280, height: int = 720) -> bool:
    if Image is None or np is None:
        return False
    heat = np.zeros((height, width), dtype=float)
    if not LOG.exists():
        return False
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except Exception:
            continue
        bbox = data.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        heat[y1:y2, x1:x2] += data.get("count", 1)
    if not heat.any():
        return False
    heat_img = (heat / heat.max() * 255).astype("uint8")
    img = Image.fromarray(heat_img, mode="L")
    img.save(out_path)
    return True


if __name__ == "__main__":  # pragma: no cover - manual
    generate_heatmap(Path("ocr_heatmap.png"))
